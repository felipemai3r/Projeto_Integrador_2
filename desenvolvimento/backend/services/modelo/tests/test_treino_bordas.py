"""Criterio de publicacao (RN07) e baselines, com um modelo falso de erro conhecido.

O modelo falso preve `fator * y_real`: o erro e (fator - 1) * y, entao a razao entre o RMSE do
modelo e o da persistencia (que preve variacao zero) vale exatamente |1 - fator|.
"""

import numpy as np
import pandas as pd
import pytest

from modelo import treino
from modelo.treino import (
    ALFAS_INTERVALO,
    COLUNAS_OBRIGATORIAS,
    DIAS_MINIMOS,
    MARGEM_SOBRE_PERSISTENCIA,
    MIN_NAO_NULOS,
    N_DOBRAS,
    REGIMES,
    avaliar_horizonte,
    calibrar_intervalo,
    cm_br,
    colunas_chuva_6h,
    colunas_usaveis,
    preparar,
    regime_chuva,
    regime_da_linha,
)


def horas(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")


def dados(n: int, semente: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(semente)
    X = pd.DataFrame(
        {"taxa_3h_cm_h": rng.normal(0, 2, n), "chuva": rng.gamma(1.0, 2.0, n)}, index=horas(n)
    )
    y = pd.Series(rng.normal(0, 10, n), index=horas(n))
    return X, y


class ModeloFalso:
    """Preve fator * y_real. Anota os indices usados no treino e no teste de cada dobra."""

    historico: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def __init__(self, y: pd.Series, fator: float) -> None:
        self.y, self.fator = y, fator
        self.ultimo_treino: pd.Timestamp | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModeloFalso":
        self.ultimo_treino = X.index.max()
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.ultimo_treino is not None and len(X) < len(self.y):
            ModeloFalso.historico.append((self.ultimo_treino, X.index.min()))
        return (self.fator * self.y.loc[X.index]).to_numpy()


@pytest.fixture
def com_fator(monkeypatch: pytest.MonkeyPatch):
    ModeloFalso.historico = []

    def instalar(y: pd.Series, fator: float) -> None:
        monkeypatch.setattr(treino, "novo_pipeline", lambda h=1: ModeloFalso(y, fator))

    return instalar


def avaliar(n: int, fator: float, h: int, com_fator) -> treino.Resultado:
    X, y = dados(n)
    com_fator(y, fator)
    return avaliar_horizonte(X, y, h)


# ---------- constantes e formatacao ----------


def test_constantes_do_criterio() -> None:
    assert MARGEM_SOBRE_PERSISTENCIA == 0.05 and N_DOBRAS == 5
    assert DIAS_MINIMOS == 60  # o valor da RN07 (ja nao e o temporario de 45)
    assert COLUNAS_OBRIGATORIAS == ("nivel_m", "taxa_1h_cm", "taxa_3h_cm_h")
    assert MIN_NAO_NULOS == 50
    assert ALFAS_INTERVALO == (0.025, 0.015, 0.01, 0.005, 0.0025)


@pytest.mark.parametrize(
    ("valor", "texto"),
    [(45.2, "45,20"), (0.0, "0,00"), (None, "0,00"), (1234.567, "1234,57"), (0.005, "0,01")],
)
def test_cm_br_usa_virgula_e_duas_casas(valor: float | None, texto: str) -> None:
    assert cm_br(valor) == texto


# ---------- preparar ----------


def test_preparar_descarta_nan_em_obrigatoria_ou_em_y_e_ordena_no_tempo() -> None:
    X, y = dados(10)
    X.iloc[2, 0] = np.nan  # taxa_3h_cm_h: obrigatoria
    y.iloc[5] = np.nan
    embaralhado = X.sample(frac=1.0, random_state=1)
    Xc, yc = preparar(embaralhado, y)
    assert len(Xc) == 8 and Xc.index.is_monotonic_increasing
    assert list(Xc.index) == list(yc.index)
    assert "__y" not in Xc.columns


def test_preparar_mantem_linha_com_nan_numa_coluna_nao_obrigatoria() -> None:
    X, y = dados(10)
    X.iloc[2, 1] = np.nan  # "chuva": o modelo aceita NaN
    Xc, _ = preparar(X, y)
    assert len(Xc) == 10 and np.isnan(Xc["chuva"].iloc[2])


def test_preparar_descarta_linha_sem_qualquer_das_tres_obrigatorias() -> None:
    X, y = dados(12)
    X = X.assign(nivel_m=2.0, taxa_1h_cm=0.1)
    X.iloc[1, X.columns.get_loc("nivel_m")] = np.nan
    X.iloc[4, X.columns.get_loc("taxa_1h_cm")] = np.nan
    X.iloc[7, X.columns.get_loc("taxa_3h_cm_h")] = np.nan
    Xc, yc = preparar(X, y)
    assert len(Xc) == 9 and len(yc) == 9
    assert not Xc[list(COLUNAS_OBRIGATORIAS)].isna().any().any()


def test_preparar_alinha_x_e_y_pelo_indice_e_descarta_o_que_nao_casa() -> None:
    X, y = dados(10)
    Xc, yc = preparar(X, y.iloc[:7])  # y mais curto: as 3 ultimas linhas de X ficam sem alvo
    assert len(Xc) == 7 and len(yc) == 7


# ---------- criterio de publicacao ----------


def test_poucas_horas_nao_valida_e_nao_treina_modelo_final() -> None:
    X, y = dados(N_DOBRAS * 48 - 1)
    r = avaliar_horizonte(X, y, 3)
    assert r.publicar is False and "Poucos dados" in r.motivo
    assert r.pipeline is None and r.rmse_cm is None and r.faixa_treino == {}
    assert r.amostras == N_DOBRAS * 48 - 1 and r.colunas == ["taxa_3h_cm_h", "chuva"]


def test_no_minimo_de_horas_para_validar_ja_calcula_as_metricas(com_fator) -> None:
    r = avaliar(N_DOBRAS * 48, 0.5, 3, com_fator)
    assert r.rmse_cm is not None and r.rmse_persistencia_cm is not None
    assert "Poucos dados" not in r.motivo


def test_modelo_perfeito_com_dias_suficientes_e_publicado(com_fator) -> None:
    r = avaliar(24 * DIAS_MINIMOS, 1.0, 3, com_fator)
    assert r.publicar is True and r.rmse_cm == pytest.approx(0.0)
    assert r.dias_uteis == DIAS_MINIMOS
    assert r.motivo == "Superou a persistência na validação."
    assert r.pipeline is not None and set(r.faixa_treino) == {"taxa_3h_cm_h", "chuva"}


def test_um_dia_a_menos_que_o_minimo_nao_publica_mesmo_com_modelo_perfeito(com_fator) -> None:
    r = avaliar(24 * (DIAS_MINIMOS - 1), 1.0, 3, com_fator)
    assert r.publicar is False
    assert f"Só há {DIAS_MINIMOS - 1} dias" in r.motivo and "mínimo para publicar" in r.motivo
    assert r.pipeline is not None  # o modelo e treinado e guardado como NAO publicado


def test_uma_hora_a_menos_que_o_minimo_nao_publica(com_fator) -> None:
    r = avaliar(24 * DIAS_MINIMOS - 1, 1.0, 3, com_fator)
    assert r.publicar is False


def test_margem_de_5_por_cento_sobre_a_persistencia(com_fator) -> None:
    n = 24 * (DIAS_MINIMOS + 5)
    # |1 - fator| = razao RMSE modelo / persistencia
    assert avaliar(n, 1 - 0.9499, 3, com_fator).publicar is True  # 5,01% melhor
    assert avaliar(n, 1 - 0.9501, 3, com_fator).publicar is False  # 4,99% melhor: nao basta


def test_empatar_com_a_persistencia_nao_publica_e_a_mensagem_traz_os_dois_erros(com_fator) -> None:
    r = avaliar(24 * (DIAS_MINIMOS + 5), 0.0, 3, com_fator)  # preve zero = persistencia
    assert r.rmse_cm == pytest.approx(r.rmse_persistencia_cm)
    assert r.publicar is False and "não superou a persistência" in r.motivo
    esperado = cm_br(r.rmse_cm)
    assert f"erro de {esperado} cm contra {cm_br(r.rmse_persistencia_cm)} cm" in r.motivo


def test_modelo_pior_que_a_persistencia_nao_publica(com_fator) -> None:
    r = avaliar(24 * (DIAS_MINIMOS + 5), 3.0, 3, com_fator)  # erro de 2 * y
    assert r.publicar is False and r.rmse_cm > r.rmse_persistencia_cm


def test_falta_de_dias_vence_a_falta_de_ganho_na_mensagem(com_fator) -> None:
    r = avaliar(24 * 10 * 2, 3.0, 3, com_fator)  # poucos dias E modelo ruim
    assert "mínimo para publicar" in r.motivo


# ---------- baselines e metricas ----------


def test_persistencia_e_o_rms_do_alvo_nas_dobras_de_teste(com_fator) -> None:
    X, y = dados(24 * 60)
    com_fator(y, 0.5)
    r = avaliar_horizonte(X, y, 3)
    # as dobras de teste cobrem as 5/6 ultimas partes da serie, nao a serie toda
    teste = y.iloc[len(y) // 6 :].to_numpy()
    assert r.rmse_persistencia_cm == pytest.approx(float(np.sqrt(np.mean(teste**2))), rel=0.02)
    assert r.rmse_cm == pytest.approx(0.5 * r.rmse_persistencia_cm, rel=1e-6)


def test_baseline_de_tendencia_extrapola_a_taxa_de_3h_vezes_o_horizonte(com_fator) -> None:
    X, _ = dados(24 * 60)
    h = 6
    y = X["taxa_3h_cm_h"] * h  # a tendencia acerta exatamente
    com_fator(y, 0.5)
    r = avaliar_horizonte(X, y, h)
    assert r.rmse_tendencia_cm == pytest.approx(0.0, abs=1e-9)
    assert r.rmse_persistencia_cm > 1.0


def test_mae_e_desvio_residual_acompanham_o_erro_do_modelo(com_fator) -> None:
    r = avaliar(24 * 60, 0.5, 3, com_fator)
    assert r.mae_cm is not None and r.desvio_residual_cm is not None
    assert 0 < r.mae_cm <= r.rmse_cm  # MAE nunca passa o RMSE
    assert r.desvio_residual_cm <= r.rmse_cm + 1e-9


def test_faixa_de_treino_e_o_minimo_e_maximo_de_cada_coluna(com_fator) -> None:
    X, y = dados(24 * 60)
    com_fator(y, 0.5)
    r = avaliar_horizonte(X, y, 3)
    assert r.faixa_treino["chuva"] == (float(X["chuva"].min()), float(X["chuva"].max()))
    assert r.colunas == list(X.columns)


def test_validacao_deixa_uma_folga_de_h_horas_entre_treino_e_teste(com_fator) -> None:
    h = 12
    avaliar(24 * 60, 0.5, h, com_fator)
    assert len(ModeloFalso.historico) == N_DOBRAS
    for ultimo_treino, primeiro_teste in ModeloFalso.historico:
        assert primeiro_teste - ultimo_treino > pd.Timedelta(hours=h)  # gap respeitado


def test_dobras_de_teste_vem_sempre_depois_das_de_treino(com_fator) -> None:
    avaliar(24 * 60, 0.5, 3, com_fator)
    inicios = [t for _, t in ModeloFalso.historico]
    assert inicios == sorted(inicios) and len(set(inicios)) == N_DOBRAS


def test_linhas_com_nan_nao_contam_nas_amostras_nem_nos_dias(com_fator) -> None:
    X, y = dados(24 * 60)
    X.iloc[:24, 0] = np.nan  # um dia inteiro sem taxa
    com_fator(y, 0.5)
    r = avaliar_horizonte(X, y, 3)
    assert r.amostras == 24 * 59 and r.dias_uteis == 59.0


# ---------- colunas usaveis (>= 50 nao nulos) ----------


def test_coluna_com_menos_de_50_valores_nao_nulos_sai_e_com_50_fica() -> None:
    X, _ = dados(200)
    X["rala"] = np.where(np.arange(200) < MIN_NAO_NULOS - 1, 1.0, np.nan)
    X["limite"] = np.where(np.arange(200) < MIN_NAO_NULOS, 1.0, np.nan)
    X["vazia"] = np.nan
    assert colunas_usaveis(X) == ["taxa_3h_cm_h", "chuva", "limite"]


def test_obrigatoria_nunca_sai_nem_em_treino_minusculo() -> None:
    X, _ = dados(20)  # menos de 50 linhas: nada passaria do limite
    assert colunas_usaveis(X) == ["taxa_3h_cm_h"]


def test_cada_dobra_descarta_as_colunas_ralas_do_proprio_treino(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    X, y = dados(24 * 60)
    X["tardia"] = np.where(np.arange(len(X)) >= 24 * 40, 1.0, np.nan)  # so existe no fim
    vistos: list[list[str]] = []

    class Espiao(ModeloFalso):
        def fit(self, X: pd.DataFrame, y: pd.Series) -> "Espiao":
            vistos.append(list(X.columns))
            return super().fit(X, y)

    monkeypatch.setattr(treino, "novo_pipeline", lambda h=1: Espiao(y, 0.5))
    r = avaliar_horizonte(X, y, 3)
    assert len(vistos) == N_DOBRAS + 1  # cinco dobras e o modelo final
    assert "tardia" not in vistos[0]  # a primeira dobra treina antes de ela existir
    assert "tardia" in vistos[-1] and "tardia" in r.colunas  # o final a usa
    assert r.colunas == vistos[-1] and set(r.faixa_treino) == set(r.colunas)


def test_linhas_com_nan_em_coluna_comum_continuam_no_treino(com_fator) -> None:
    X, y = dados(24 * 60)
    X.iloc[:24, 1] = np.nan  # um dia inteiro sem "chuva"
    com_fator(y, 0.5)
    r = avaliar_horizonte(X, y, 3)
    assert r.amostras == 24 * 60 and "chuva" in r.colunas


# ---------- regime de chuva ----------


def test_colunas_chuva_6h_pega_so_a_janela_de_6_horas() -> None:
    cols = ["chuva_local_6h", "chuva_local_168h", "chuva_serra_indios_6h", "chuva_emma_16h", "x_6h"]
    assert colunas_chuva_6h(cols) == ["chuva_local_6h", "chuva_serra_indios_6h"]


@pytest.mark.parametrize(
    ("chuvas", "regime"),
    [
        ([0.0, 0.0], "seco"),
        ([0.99, 0.5], "seco"),
        ([1.0, 0.0], "chuva"),  # 1 mm ja e chuva
        ([0.2, 9.99], "chuva"),
        ([10.0, 0.0], "chuva_forte"),  # 10 mm ja e chuva forte
        ([0.0, 35.0], "chuva_forte"),  # vale o MAIOR entre os pontos
        ([np.nan, 0.0], "seco"),  # NaN so e ignorado se algum ponto tem leitura
        ([np.nan, 4.0], "chuva"),
        ([np.nan, np.nan], "chuva_forte"),  # tudo desconhecido: lado conservador
    ],
)
def test_regime_pelo_maior_acumulado_de_6h(chuvas: list[float], regime: str) -> None:
    assert regime_chuva(np.array([chuvas]))[0] == regime


def test_regime_sem_nenhuma_coluna_de_chuva_e_chuva_forte() -> None:
    assert list(regime_chuva(np.empty((3, 0)))) == ["chuva_forte"] * 3
    assert regime_da_linha(pd.Series({"nivel_m": 1.0}), ["nivel_m"]) == "chuva_forte"


def test_regime_da_linha_so_olha_as_colunas_do_modelo() -> None:
    linha = pd.Series({"chuva_local_6h": 0.0, "chuva_serra_indios_6h": 50.0})
    assert regime_da_linha(linha, ["chuva_local_6h"]) == "seco"  # a serra nao e do modelo
    assert regime_da_linha(linha, ["chuva_local_6h", "chuva_serra_indios_6h"]) == "chuva_forte"
    # coluna do modelo que a linha nao tem conta como NaN (nunca como zero)
    assert regime_da_linha(pd.Series({"x": 1.0}), ["chuva_local_6h"]) == "chuva_forte"


# ---------- intervalo por regime ----------


def residuos_sinteticos(n: int = 3000, semente: int = 5):
    """Seco com erro pequeno, chuva media, chuva forte grande; regimes embaralhados no tempo."""
    rng = np.random.default_rng(semente)
    regimes = rng.choice(np.array(REGIMES, dtype=object), size=n, p=[0.6, 0.3, 0.1])
    escala = {"seco": 2.0, "chuva": 10.0, "chuva_forte": 25.0}
    res = np.array([rng.normal(0, escala[g]) for g in regimes])
    return res, regimes


def test_intervalo_fica_mais_largo_quanto_mais_chove() -> None:
    res, regimes = residuos_sinteticos()
    por_regime, alfa, cobertura = calibrar_intervalo(res, regimes)
    larg = {g: hi - lo for g, (lo, hi) in por_regime.items()}
    assert larg["seco"] < larg["chuva"] < larg["chuva_forte"]
    assert set(por_regime) == set(REGIMES) and alfa in ALFAS_INTERVALO
    assert all(lo < 0 < hi for lo, hi in por_regime.values())
    assert cobertura >= 0.95


def test_residuos_estaveis_ficam_no_primeiro_alfa() -> None:
    rng = np.random.default_rng(4)
    res = rng.normal(0, 1, 6000) * np.where(np.arange(6000) < 3600, 1.0, 0.7)  # fim mais calmo
    _, alfa, cobertura = calibrar_intervalo(res, np.full(6000, "seco", dtype=object))
    assert alfa == ALFAS_INTERVALO[0] and cobertura >= 0.95


def test_residuo_que_piora_no_trecho_final_empurra_o_alfa_para_baixo() -> None:
    """A chuva futura nao e conhecida: no fim o erro cresce e 2,5/97,5 deixa de cobrir 95%."""
    rng = np.random.default_rng(1)
    res = rng.normal(0, 1, 6000) * np.where(np.arange(6000) < 3600, 1.0, 1.25)
    _, alfa, cobertura = calibrar_intervalo(res, np.full(6000, "seco", dtype=object))
    assert alfa < ALFAS_INTERVALO[0] and cobertura >= 0.95


def test_se_nenhum_alfa_cobre_fica_o_menor() -> None:
    rng = np.random.default_rng(2)
    res = np.concatenate([rng.normal(0, 1, 3000), rng.normal(0, 50, 2000)])  # fim bem pior
    _, alfa, cobertura = calibrar_intervalo(res, np.full(5000, "seco", dtype=object))
    assert alfa == ALFAS_INTERVALO[-1] and cobertura < 0.95


def test_regime_com_menos_de_30_residuos_usa_os_quantis_de_todos() -> None:
    rng = np.random.default_rng(3)
    res = rng.normal(0, 4.0, 2000)
    regimes = np.full(2000, "seco", dtype=object)
    regimes[:10] = "chuva_forte"  # so 10 residuos
    por_regime, _, _ = calibrar_intervalo(res, regimes)
    # "chuva" nao tem residuo nenhum e "chuva_forte" tem 10: ambos herdam os limites gerais
    assert por_regime["chuva"] == por_regime["chuva_forte"]
    assert por_regime["chuva"][1] > por_regime["seco"][1] * 0.9


def test_quantis_finais_usam_todos_os_residuos_e_a_cobertura_so_os_ultimos_40() -> None:
    res = np.concatenate([np.full(60, -100.0), np.full(40, 1.0)])
    regimes = np.full(100, "seco", dtype=object)
    por_regime, _, cobertura = calibrar_intervalo(res, regimes)
    # calibrado nos primeiros 60 (todos -100), o trecho final (1.0) fica descoberto
    assert cobertura == 0.0
    # mas os limites finais olham os 100 residuos
    assert por_regime["seco"][0] == -100.0 and por_regime["seco"][1] >= 1.0


def test_avaliacao_devolve_intervalo_alfa_cobertura_e_obrigatorias(com_fator) -> None:
    X, y = dados(24 * 60)
    X["chuva_local_6h"] = np.abs(X["chuva"])  # da regime ao intervalo
    com_fator(y, 0.5)
    r = avaliar_horizonte(X, y, 3)
    assert set(r.intervalo_por_regime) == set(REGIMES)
    assert r.alfa_intervalo in ALFAS_INTERVALO and 0.0 <= (r.cobertura_validacao or 0) <= 1.0
    assert r.colunas_obrigatorias == ["taxa_3h_cm_h"] and r.aceita_nan is True
    assert r.desvio_residual_cm is not None  # mantido por compatibilidade
    for lo, hi in r.intervalo_por_regime.values():
        assert lo <= 0 <= hi  # o erro do modelo falso (0,5 y) e simetrico em torno de zero


def test_poucos_dados_nao_calibra_intervalo() -> None:
    X, y = dados(N_DOBRAS * 48 - 1)
    r = avaliar_horizonte(X, y, 3)
    assert r.intervalo_por_regime == {} and r.alfa_intervalo is None


def test_intervalo_cobre_de_fato_com_o_modelo_falso_de_erro_conhecido(com_fator) -> None:
    X, y = dados(24 * 90)
    com_fator(y, 0.5)  # residuo = real - previsto = 0,5 * y
    r = avaliar_horizonte(X, y, 3)
    # sem coluna de chuva de 6 h o regime e sempre chuva_forte (3 limites iguais ou herdados)
    lo, hi = r.intervalo_por_regime["chuva_forte"]
    res = 0.5 * y.iloc[len(y) // 6 :].to_numpy()
    assert np.mean((res >= lo) & (res <= hi)) >= 0.94


# ---------- modelo real (gradient boosting) ----------


def test_pipeline_real_e_hgb_determinista_e_sem_early_stopping() -> None:
    from sklearn.ensemble import HistGradientBoostingRegressor

    modelo = treino.novo_pipeline(3)
    assert isinstance(modelo, HistGradientBoostingRegressor)
    p = modelo.get_params()
    assert (p["loss"], p["max_iter"], p["learning_rate"]) == ("absolute_error", 600, 0.04)
    assert (p["max_leaf_nodes"], p["min_samples_leaf"], p["l2_regularization"]) == (15, 80, 2.0)
    assert p["early_stopping"] is False and p["random_state"] == 0


def test_pipeline_real_aprende_e_aceita_nan_sem_virar_zero() -> None:
    rng = np.random.default_rng(0)
    X, _ = dados(24 * 30)
    y = 4.0 * X["chuva"] + 0.5 * X["taxa_3h_cm_h"]
    modelo = treino.novo_pipeline(3)
    modelo.fit(X, y)  # type: ignore[attr-defined]
    pred = modelo.predict(X)  # type: ignore[attr-defined]
    assert np.corrcoef(pred, y)[0, 1] > 0.9
    com_nan = X.assign(chuva=np.where(rng.random(len(X)) < 0.3, np.nan, X["chuva"]))
    modelo2 = treino.novo_pipeline(3)
    modelo2.fit(com_nan, y)  # type: ignore[attr-defined]
    saida = modelo2.predict(com_nan.iloc[:5])  # type: ignore[attr-defined]
    assert np.isfinite(saida).all()


def test_mesmo_dado_gera_o_mesmo_modelo() -> None:
    X, _ = dados(24 * 20)
    y = 4.0 * X["chuva"]
    a, b = treino.novo_pipeline(3), treino.novo_pipeline(3)
    a.fit(X, y)  # type: ignore[attr-defined]
    b.fit(X, y)  # type: ignore[attr-defined]
    np.testing.assert_array_equal(a.predict(X), b.predict(X))  # type: ignore[attr-defined]


def test_confianca_e_95_ate_6h_e_80_em_12_e_24h() -> None:
    assert [treino.confianca_do_horizonte(h) for h in (1, 3, 6, 12, 24)] == [
        0.95,
        0.95,
        0.95,
        0.80,
        0.80,
    ]


def test_alfas_candidatos_partem_do_nominal_e_alargam_as_caudas() -> None:
    assert treino.alfas_candidatos(0.95) == ALFAS_INTERVALO
    a80 = treino.alfas_candidatos(0.80)
    assert a80[0] == pytest.approx(0.10) and list(a80) == sorted(a80, reverse=True)


def test_intervalo_de_80_porcento_e_mais_estreito_e_cobre_80() -> None:
    rng = np.random.default_rng(7)
    res = rng.standard_t(3, 6000)  # caudas pesadas, como o erro em 24 h
    regimes = np.full(6000, "seco", dtype=object)
    l95, _, c95 = calibrar_intervalo(res, regimes, 0.95)
    l80, alfa80, c80 = calibrar_intervalo(res, regimes, 0.80)
    assert c95 >= 0.95 and c80 >= 0.80 and alfa80 >= 0.05
    assert l80["seco"][1] - l80["seco"][0] < 0.6 * (l95["seco"][1] - l95["seco"][0])
