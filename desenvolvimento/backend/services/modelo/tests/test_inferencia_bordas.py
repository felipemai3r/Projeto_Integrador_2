"""Inferencia: colunas faltando, extrapolacao, cenarios e imputacao, nos limites."""

import numpy as np
import pandas as pd
import pytest

from modelo.features import JANELAS_CHUVA_H, PONTOS_CHUVA
from modelo.inferencia import (
    JANELA_IMPUTACAO_H,
    MAX_HORAS_IMPUTADAS,
    MIN_VIZINHOS_IMPUTACAO,
    ROTULO_DE_CODIGO,
    aplicar_cenario,
    colunas_exigidas,
    colunas_faltando,
    extrapola,
    imputar_chuva,
    intervalo_cm,
    obrigatorias_do_artefato,
    prever_variacao_cm,
)


class PipelineFalso:
    """Guarda o que recebeu e devolve a soma da linha (assim a ordem das colunas nao importa)."""

    def __init__(self) -> None:
        self.recebido: pd.DataFrame | None = None

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self.recebido = X
        return np.array([float(X.iloc[0].sum())])


def artefato(colunas: list[str], faixa: dict | None = None) -> dict:
    a: dict = {"pipeline": PipelineFalso(), "colunas": colunas}
    if faixa is not None:
        a["faixa_treino"] = faixa
    return a


# ---------- constantes ----------


def test_constantes_da_imputacao() -> None:
    assert JANELA_IMPUTACAO_H == 168 and MAX_HORAS_IMPUTADAS == 24 and MIN_VIZINHOS_IMPUTACAO == 2
    assert ROTULO_DE_CODIGO is PONTOS_CHUVA


# ---------- prever_variacao_cm ----------


def test_previsao_usa_so_as_colunas_do_modelo_na_ordem_do_artefato() -> None:
    a = artefato(["b", "a"])
    linha = pd.Series({"a": 1.0, "b": 10.0, "extra": 999.0})
    assert prever_variacao_cm(a, linha) == 11.0
    assert list(a["pipeline"].recebido.columns) == ["b", "a"]
    assert a["pipeline"].recebido.shape == (1, 2)


def test_previsao_devolve_float_python_mesmo_com_linha_inteira() -> None:
    v = prever_variacao_cm(artefato(["a"]), pd.Series({"a": 2}))
    assert isinstance(v, float) and v == 2.0


def test_previsao_sem_coluna_exigida_levanta_keyerror_em_vez_de_chutar() -> None:
    with pytest.raises(KeyError):
        prever_variacao_cm(artefato(["a", "falta"]), pd.Series({"a": 1.0}))


# ---------- colunas_faltando ----------


def test_coluna_ausente_e_coluna_nan_contam_como_faltando_na_ordem_do_modelo() -> None:
    a = artefato(["z", "a", "m", "b"])
    linha = pd.Series({"a": np.nan, "b": 1.0, "z": 3.0})
    assert colunas_faltando(a, linha) == ["a", "m"]


def test_zero_nao_e_falta() -> None:
    assert colunas_faltando(artefato(["a"]), pd.Series({"a": 0.0})) == []


def test_modelo_sem_colunas_nunca_tem_falta() -> None:
    assert colunas_faltando(artefato([]), pd.Series({"a": np.nan})) == []


def test_coluna_extra_nan_que_o_modelo_nao_usa_nao_atrapalha() -> None:
    assert (
        colunas_faltando(artefato(["a"]), pd.Series({"a": 1.0, "chuva_serra_vencida_3h": np.nan}))
        == []
    )


# ---------- extrapola ----------


FAIXA = {"a": (0.0, 10.0), "b": (-5.0, 5.0)}


def test_valor_exatamente_nos_extremos_da_faixa_nao_e_extrapolacao() -> None:
    a = artefato(["a", "b"], FAIXA)
    assert extrapola(a, pd.Series({"a": 0.0, "b": 5.0})) == []
    assert extrapola(a, pd.Series({"a": 10.0, "b": -5.0})) == []


def test_valor_logo_fora_da_faixa_e_extrapolacao_nos_dois_lados() -> None:
    a = artefato(["a", "b"], FAIXA)
    assert extrapola(a, pd.Series({"a": 10.0001, "b": 0.0})) == ["a"]
    assert extrapola(a, pd.Series({"a": 5.0, "b": -5.0001})) == ["b"]


def test_lista_todas_as_colunas_fora_da_faixa() -> None:
    assert extrapola(artefato(["a", "b"], FAIXA), pd.Series({"a": 99.0, "b": -99.0})) == ["a", "b"]


def test_artefato_sem_faixa_de_treino_nao_acusa_nada() -> None:
    assert extrapola(artefato(["a"]), pd.Series({"a": 1e9})) == []


def test_coluna_da_faixa_que_a_linha_nao_tem_e_ignorada() -> None:
    assert extrapola(artefato(["a"], {"a": (0.0, 1.0)}), pd.Series({"outra": 5.0})) == []


# ---------- aplicar_cenario ----------


def linha_base() -> pd.Series:
    dados = {f"chuva_local_{j}h": 1.0 for j in JANELAS_CHUVA_H}
    dados |= {f"chuva_serra_indios_{j}h": 0.5 for j in JANELAS_CHUVA_H}
    dados |= {"nivel_m": 2.0, "taxa_1h_cm": 3.0}
    return pd.Series(dados)


def test_janela_igual_ao_cenario_recebe_o_total_e_as_menores_a_fracao() -> None:
    nova = aplicar_cenario(linha_base(), {"DCSC-00043": 60.0}, 6)
    assert nova["chuva_local_6h"] == pytest.approx(60.0)
    assert nova["chuva_local_1h"] == pytest.approx(10.0)
    assert nova["chuva_local_3h"] == pytest.approx(30.0)


def test_janela_maior_que_o_cenario_nunca_diminui_o_ja_acumulado() -> None:
    base = linha_base()
    base["chuva_local_24h"] = 80.0
    nova = aplicar_cenario(base, {"DCSC-00043": 10.0}, 6)
    assert nova["chuva_local_24h"] == 80.0  # ja choveu mais que o cenario
    assert nova["chuva_local_48h"] == 10.0  # o cenario supera o 1,0 que havia


def test_chuva_zero_zera_as_janelas_curtas_mas_preserva_as_longas_com_chuva_real() -> None:
    base = linha_base()
    base["chuva_local_72h"] = 25.0
    nova = aplicar_cenario(base, {"DCSC-00043": 0.0}, 3)
    assert nova["chuva_local_1h"] == 0.0 and nova["chuva_local_3h"] == 0.0
    assert nova["chuva_local_72h"] == 25.0


def test_ponto_fora_do_cadastro_e_ignorado() -> None:
    base = linha_base()
    pd.testing.assert_series_equal(aplicar_cenario(base, {"DCSC-99999": 500.0}, 6), base)


def test_ponto_cadastrado_mas_sem_colunas_na_linha_e_ignorado() -> None:
    base = linha_base()  # nao tem colunas da Dona Emma
    pd.testing.assert_series_equal(aplicar_cenario(base, {"DCSC-00037": 50.0}, 6), base)


def test_nao_altera_a_linha_original() -> None:
    base = linha_base()
    copia = base.copy()
    aplicar_cenario(base, {"DCSC-00043": 99.0, "DC-PEU-003": 99.0}, 6)
    pd.testing.assert_series_equal(base, copia)


def test_serra_recebe_cenario_como_qualquer_ponto_e_nivel_e_taxa_ficam() -> None:
    nova = aplicar_cenario(linha_base(), {"DC-PEU-003": 30.0}, 6)
    assert nova["chuva_serra_indios_6h"] == pytest.approx(30.0)
    assert nova["nivel_m"] == 2.0 and nova["taxa_1h_cm"] == 3.0
    assert nova["chuva_local_6h"] == 1.0  # os outros pontos nao mudam


def test_interacoes_sao_recalculadas_com_os_valores_do_cenario() -> None:
    base = linha_base()
    base["chuva_emma_6h"] = 1.0
    base["chuva_boiteux_6h"] = 1.0
    base["emma_x_boiteux_6h"] = 1.0
    base["nivel_ibirama_m"] = 2.0
    base["ibirama_x_chuva_local_3h"] = 2.0
    nova = aplicar_cenario(base, {"DCSC-00037": 10.0, "DCSC-00021": 20.0, "DCSC-00043": 12.0}, 6)
    assert nova["emma_x_boiteux_6h"] == pytest.approx(200.0)
    assert nova["ibirama_x_chuva_local_3h"] == pytest.approx(2.0 * 6.0)  # 12 mm * 3/6 = 6


def test_interacao_nao_e_recalculada_se_faltar_alguma_origem() -> None:
    base = linha_base()
    base["chuva_emma_6h"] = 1.0
    base["emma_x_boiteux_6h"] = 7.0  # sem chuva_boiteux_6h na linha
    assert aplicar_cenario(base, {"DCSC-00037": 10.0}, 6)["emma_x_boiteux_6h"] == 7.0


def test_cenario_vazio_devolve_copia_igual() -> None:
    base = linha_base()
    pd.testing.assert_series_equal(aplicar_cenario(base, {}, 6), base)


# ---------- imputar_chuva ----------


def horas(valores: list[float]) -> pd.Series:
    idx = pd.date_range("2026-10-01", periods=len(valores), freq="1h", tz="UTC")
    return pd.Series(valores, idx, dtype=float)


def test_exatamente_tres_pontos_ja_permitem_imputar_com_dois_vizinhos() -> None:
    p = {"A": horas([1.0, np.nan, 1.0]), "B": horas([2.0] * 3), "C": horas([4.0] * 3)}
    novo, horas_ = imputar_chuva(p)
    assert novo["A"].iloc[1] == 3.0 and list(horas_["A"]) == [p["A"].index[1]]


def test_min_vizinhos_maior_exige_mais_pontos_com_dado() -> None:
    p = {"A": horas([1.0, np.nan]), "B": horas([2.0, 2.0]), "C": horas([4.0, 4.0])}
    novo, horas_ = imputar_chuva(p, min_vizinhos=3)
    assert np.isnan(novo["A"].iloc[1]) and horas_ == {}


def test_hora_imputada_usa_so_vizinhos_com_dado_naquela_hora() -> None:
    p = {
        "A": horas([1.0, np.nan, 1.0]),
        "B": horas([2.0, 2.0, 2.0]),
        "C": horas([6.0, np.nan, 6.0]),
        "D": horas([10.0, 4.0, 10.0]),
    }
    novo, _ = imputar_chuva(p)
    assert novo["A"].iloc[1] == pytest.approx(3.0)  # media de B e D (C tambem sem dado)


def test_zero_medido_e_dado_valido_e_entra_na_media_dos_vizinhos() -> None:
    p = {"A": horas([np.nan, 1.0]), "B": horas([0.0, 1.0]), "C": horas([0.0, 1.0])}
    novo, _ = imputar_chuva(p)
    assert novo["A"].iloc[0] == 0.0  # dois vizinhos secos: estimativa seca, nao NaN


def test_ponto_ja_completo_volta_o_mesmo_objeto_e_nao_aparece_nas_horas_estimadas() -> None:
    p = {"A": horas([1.0] * 5), "B": horas([2.0] * 5), "C": horas([3.0, np.nan, 3.0, 3.0, 3.0])}
    novo, horas_ = imputar_chuva(p)
    assert novo["A"] is p["A"] and "A" not in horas_


def test_so_conta_o_limite_de_horas_dentro_da_janela_final() -> None:
    n = 400
    p = {c: horas([1.0] * n) for c in "ABC"}
    p["A"].iloc[0:200] = np.nan  # lacuna antiga e grande, fora das ultimas 168 h
    novo, horas_ = imputar_chuva(p)
    assert novo["A"].iloc[:200].isna().all() and horas_ == {}  # nada a fazer na janela final


def test_lacuna_exatamente_no_limite_e_imputada() -> None:
    p = {c: horas([1.0] * 100) for c in "ABC"}
    p["A"].iloc[-MAX_HORAS_IMPUTADAS:] = np.nan
    novo, horas_ = imputar_chuva(p)
    assert novo["A"].notna().all() and len(horas_["A"]) == MAX_HORAS_IMPUTADAS


# ---------- modelo que aceita NaN (ADR 0006) x modelo antigo ----------


class PipelineNaN:
    """Guarda o que recebeu e soma ignorando NaN (como um modelo que lida com valor ausente)."""

    def __init__(self) -> None:
        self.recebido: pd.DataFrame | None = None

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self.recebido = X
        return np.array([float(np.nansum(X.to_numpy()))])


def novo(colunas: list[str], obrigatorias: list[str], **extra) -> dict:  # noqa: ANN003
    return {
        "pipeline": PipelineNaN(),
        "colunas": colunas,
        "aceita_nan": True,
        "colunas_obrigatorias": obrigatorias,
        **extra,
    }


def test_modelo_novo_exige_so_as_obrigatorias_mais_o_nivel_e_o_antigo_exige_tudo() -> None:
    a = novo(["nivel_m", "taxa_3h_cm_h", "chuva_local_6h"], ["taxa_3h_cm_h"])
    assert obrigatorias_do_artefato(a) == ["taxa_3h_cm_h"]
    assert colunas_exigidas(a) == ["taxa_3h_cm_h", "nivel_m"]
    antigo = artefato(["nivel_m", "taxa_3h_cm_h", "chuva_local_6h"])
    assert obrigatorias_do_artefato(antigo) is None  # sem `aceita_nan`: comportamento de sempre
    assert colunas_exigidas(antigo) == ["nivel_m", "taxa_3h_cm_h", "chuva_local_6h"]


def test_colunas_faltando_do_modelo_novo_ignora_chuva_vazia_mas_nao_a_obrigatoria() -> None:
    a = novo(["nivel_m", "taxa_3h_cm_h", "chuva_local_6h"], ["nivel_m", "taxa_3h_cm_h"])
    linha = pd.Series({"nivel_m": 2.0, "taxa_3h_cm_h": 1.0, "chuva_local_6h": np.nan})
    assert colunas_faltando(a, linha) == []
    assert colunas_faltando(a, linha.drop("chuva_local_6h")) == []
    assert colunas_faltando(a, linha.where(linha.index != "taxa_3h_cm_h")) == ["taxa_3h_cm_h"]
    # o modelo antigo, com a mesma linha, continua recusando a chuva vazia
    assert colunas_faltando(artefato(list(a["colunas"])), linha) == ["chuva_local_6h"]


def test_modelo_novo_recebe_nan_e_nunca_zero_nas_colunas_vazias_ou_ausentes() -> None:
    a = novo(["nivel_m", "chuva_local_6h", "chuva_serra_indios_6h"], ["nivel_m"])
    prever_variacao_cm(a, pd.Series({"nivel_m": 2.0, "chuva_local_6h": np.nan}))
    recebido = a["pipeline"].recebido
    assert list(recebido.columns) == ["nivel_m", "chuva_local_6h", "chuva_serra_indios_6h"]
    assert recebido.iloc[0].isna().tolist() == [False, True, True]  # a ausente tambem vira NaN


def test_extrapola_ignora_variavel_sem_valor() -> None:
    a = artefato(["a", "b"], {"a": (0.0, 10.0), "b": (0.0, 10.0)})
    assert extrapola(a, pd.Series({"a": np.nan, "b": 11.0})) == ["b"]
    assert extrapola(a, pd.Series({"b": 5.0})) == []  # coluna ausente: nada a sinalizar


def test_cenario_preenche_janela_longa_vazia_com_o_valor_do_cenario_sem_virar_nan() -> None:
    linha = pd.Series({"chuva_local_1h": np.nan, "chuva_local_72h": np.nan, "nivel_m": 2.0})
    nova = aplicar_cenario(linha, {"DCSC-00043": 12.0}, 6)
    assert nova["chuva_local_1h"] == pytest.approx(2.0)
    assert nova["chuva_local_72h"] == pytest.approx(12.0)  # sem leitura, nao ha o que preservar
    assert nova["nivel_m"] == 2.0


def test_cenario_deixa_nan_o_ponto_que_nao_esta_no_cenario() -> None:
    linha = pd.Series({"chuva_local_6h": 1.0, "chuva_serra_indios_6h": np.nan})
    nova = aplicar_cenario(linha, {"DCSC-00043": 12.0}, 6)
    assert np.isnan(nova["chuva_serra_indios_6h"])  # nunca zero


# ---------- intervalo_cm ----------

POR_REGIME = {"seco": [-9.0, 9.5], "chuva": [-40.0, 55.0], "chuva_forte": [-70.0, 80.0]}


def test_intervalo_cm_escolhe_o_regime_da_linha_pelas_chuvas_de_6h_do_modelo() -> None:
    a = novo(["nivel_m", "chuva_local_6h", "chuva_serra_indios_6h"], ["nivel_m"])
    a["intervalo_por_regime"] = POR_REGIME
    seco = pd.Series({"chuva_local_6h": 0.0, "chuva_serra_indios_6h": 0.5})
    assert intervalo_cm(a, seco) == (-9.0, 9.5)
    chuva = pd.Series({"chuva_local_6h": 0.0, "chuva_serra_indios_6h": 3.0})
    assert intervalo_cm(a, chuva) == (-40.0, 55.0)
    forte = pd.Series({"chuva_local_6h": 12.0, "chuva_serra_indios_6h": 3.0})
    assert intervalo_cm(a, forte) == (-70.0, 80.0)
    # sem nenhuma chuva conhecida, o lado conservador
    assert intervalo_cm(a, pd.Series({"nivel_m": 2.0})) == (-70.0, 80.0)


def test_intervalo_cm_cai_nos_metadados_e_e_none_no_modelo_antigo() -> None:
    a = novo(["nivel_m", "chuva_local_6h"], ["nivel_m"])  # artefato sem o intervalo
    linha = pd.Series({"chuva_local_6h": 0.0})
    assert intervalo_cm(a, linha) is None
    assert intervalo_cm(a, linha, {}) is None and intervalo_cm(a, linha, None) is None
    assert intervalo_cm(a, linha, {"intervalo_por_regime": POR_REGIME}) == (-9.0, 9.5)
    assert intervalo_cm(artefato(["a"]), pd.Series({"a": 1.0})) is None


def test_intervalo_cm_com_regime_ausente_no_dicionario_nao_chuta() -> None:
    a = novo(["chuva_local_6h"], [], intervalo_por_regime={"seco": [-1.0, 1.0]})
    assert intervalo_cm(a, pd.Series({"chuva_local_6h": 50.0})) is None
