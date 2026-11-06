"""Criterio de publicacao (RN07) e baselines, com um modelo falso de erro conhecido.

O modelo falso preve `fator * y_real`: o erro e (fator - 1) * y, entao a razao entre o RMSE do
modelo e o da persistencia (que preve variacao zero) vale exatamente |1 - fator|.
"""

import numpy as np
import pandas as pd
import pytest

from modelo import treino
from modelo.treino import (
    ALPHAS,
    DIAS_MINIMOS,
    MARGEM_SOBRE_PERSISTENCIA,
    N_DOBRAS,
    avaliar_horizonte,
    cm_br,
    preparar,
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
    assert tuple(sorted(ALPHAS)) == ALPHAS and len(ALPHAS) >= 5


@pytest.mark.parametrize(
    ("valor", "texto"),
    [(45.2, "45,20"), (0.0, "0,00"), (None, "0,00"), (1234.567, "1234,57"), (0.005, "0,01")],
)
def test_cm_br_usa_virgula_e_duas_casas(valor: float | None, texto: str) -> None:
    assert cm_br(valor) == texto


# ---------- preparar ----------


def test_preparar_descarta_nan_em_x_ou_em_y_e_ordena_no_tempo() -> None:
    X, y = dados(10)
    X.iloc[2, 0] = np.nan
    y.iloc[5] = np.nan
    embaralhado = X.sample(frac=1.0, random_state=1)
    Xc, yc = preparar(embaralhado, y)
    assert len(Xc) == 8 and Xc.index.is_monotonic_increasing
    assert list(Xc.index) == list(yc.index)
    assert "__y" not in Xc.columns


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


# ---------- modelo real (Ridge) ----------


def test_pipeline_real_escolhe_alpha_da_grade_e_preve_com_x_padronizado() -> None:
    X, _ = dados(24 * 30)
    y = 4.0 * X["chuva"] + 0.5 * X["taxa_3h_cm_h"]
    modelo = treino.novo_pipeline(3)
    modelo.fit(X, y)  # type: ignore[attr-defined]
    assert modelo.steps[-1][1].alpha_ in ALPHAS  # type: ignore[attr-defined]
    pred = modelo.predict(X)  # type: ignore[attr-defined]
    assert np.corrcoef(pred, y)[0, 1] > 0.99
