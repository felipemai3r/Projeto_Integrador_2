"""Variaveis do modelo: janelas de chuva, cobertura minima, vizinhos e rotulos dos pontos."""

import numpy as np
import pandas as pd
import pytest

from modelo.features import (
    ALVOS,
    HORIZONTES_H,
    JANELA_MIN_TOLERANTE_H,
    JANELAS_CHUVA_H,
    MIN_COBERTURA_LONGA,
    NIVEL_VIZINHOS,
    PONTOS_CHUVA,
    ConfigAlvo,
    alvo_deslocado,
    chuva_acumulada,
    config_alvo,
    montar_features,
    pontos_chuva,
    vizinhos_nivel,
)

PG = "DCSC-00043"
REVOLVER = "DCSC-00174"


def horas(n: int, inicio: str = "2026-10-01 00:00") -> pd.DatetimeIndex:
    return pd.date_range(inicio, periods=n, freq="1h", tz="UTC")


def serie(valores: list[float], inicio: str = "2026-10-01 00:00") -> pd.Series:
    return pd.Series(valores, horas(len(valores), inicio), dtype=float)


# ---------- chuva acumulada: cobertura minima ----------


def test_constantes_da_cobertura() -> None:
    assert MIN_COBERTURA_LONGA == 0.9 and JANELA_MIN_TOLERANTE_H == 12
    assert JANELAS_CHUVA_H == (1, 3, 6, 12, 24, 48, 72, 168)
    assert HORIZONTES_H == (1, 3, 6, 12, 24)


@pytest.mark.parametrize("janela", [1, 3, 6, 11])
def test_janela_curta_com_uma_unica_falha_dentro_dela_e_desconhecida(janela: int) -> None:
    chuva = pd.Series(1.0, horas(60))
    chuva.iloc[30] = np.nan
    r = chuva_acumulada(chuva, janela)
    assert np.isnan(r.iloc[30])  # a propria hora faltando entra em toda janela que a contem
    assert r.iloc[30 + janela] == pytest.approx(janela)  # a janela seguinte ja nao a contem


@pytest.mark.parametrize(("janela", "toleradas"), [(12, 1), (24, 2), (48, 4), (72, 7), (168, 16)])
def test_janela_longa_tolera_ate_10_por_cento_de_falhas_e_reescala(
    janela: int, toleradas: int
) -> None:
    chuva = pd.Series(1.0, horas(janela + 5))
    chuva.iloc[5 : 5 + toleradas] = np.nan  # dentro da janela que termina em janela + 3
    assert chuva_acumulada(chuva, janela).iloc[janela + 3] == pytest.approx(janela)


@pytest.mark.parametrize(("janela", "toleradas"), [(12, 1), (24, 2), (48, 4), (72, 7), (168, 16)])
def test_janela_longa_com_uma_falha_alem_da_tolerancia_e_desconhecida(
    janela: int, toleradas: int
) -> None:
    chuva = pd.Series(1.0, horas(janela + 5))
    chuva.iloc[5 : 6 + toleradas] = np.nan  # uma a mais que o tolerado
    assert np.isnan(chuva_acumulada(chuva, janela).iloc[janela + 3])


def test_reescala_preserva_a_media_horaria_das_horas_medidas() -> None:
    chuva = serie([2.0] * 12 + [np.nan] + [2.0] * 11)  # 24 h, 1 falha
    # 23 horas de 2 mm reescaladas para 24 horas: 46 * 24 / 23 = 48
    assert chuva_acumulada(chuva, 24).iloc[-1] == pytest.approx(48.0)


def test_primeiras_horas_sem_historico_suficiente_ficam_nan() -> None:
    chuva = pd.Series(1.0, horas(30))
    r = chuva_acumulada(chuva, 24)
    assert r.iloc[:21].isna().all()  # menos de 22 horas medidas (90% de 24)
    assert r.iloc[21] == pytest.approx(24.0)  # 22 horas reescaladas para 24


def test_janela_so_olha_para_tras_ate_t_inclusive() -> None:
    chuva = serie([0.0, 0.0, 0.0, 5.0, 0.0, 0.0])
    r = chuva_acumulada(chuva, 3)
    assert r.iloc[2] == 0.0 and r.iloc[3] == 5.0 and r.iloc[5] == 5.0 and r.iloc[4] == 5.0


def test_serie_vazia_devolve_vazia() -> None:
    assert chuva_acumulada(pd.Series(dtype=float, index=horas(0)), 6).empty


# ---------- configuracao dos alvos ----------


def test_cada_alvo_registrado_tem_o_proprio_codigo_na_config() -> None:
    for codigo, cfg in ALVOS.items():
        assert cfg.codigo == codigo and cfg.nome


def test_alvo_desconhecido_usa_vizinhos_padrao_interacoes_e_todo_o_historico() -> None:
    cfg = config_alvo("DCSC-99999")
    assert cfg.nivel_vizinhos == NIVEL_VIZINHOS
    assert cfg.interacoes is True and cfg.janela_dias is None


def test_vizinhos_nunca_incluem_o_proprio_alvo_mesmo_se_a_config_o_listar(monkeypatch) -> None:
    monkeypatch.setitem(
        ALVOS, "X", ConfigAlvo("X", "x", {"X": "eu", "DCSC-00043": "getulio"}, interacoes=False)
    )
    assert vizinhos_nivel("X") == {"DCSC-00043": "getulio"}
    n = serie([1.0] * 10)
    c = {PG: serie([0.0] * 10)}
    X = montar_features(c, {"X": n, "DCSC-00043": n * 2}, alvo="X")
    assert "nivel_eu_m" not in X.columns and "nivel_getulio_m" in X.columns
    assert X["nivel_m"].eq(1.0).all()


def test_vizinho_de_nivel_ausente_nos_dados_e_ignorado_sem_erro() -> None:
    n = serie(list(np.linspace(1, 2, 30)))
    X = montar_features({PG: serie([0.0] * 30)}, {PG: n})  # sem Boiteux nem Ibirama
    assert not [c for c in X.columns if "boiteux_m" in c or "ibirama_m" in c]
    assert "emma_x_boiteux_6h" not in X.columns and "ibirama_x_chuva_local_3h" not in X.columns


def test_ponto_de_chuva_fora_do_cadastro_e_ignorado() -> None:
    n = serie([1.0] * 30)
    X = montar_features({PG: serie([0.0] * 30), "DCSC-99999": serie([9.0] * 30)}, {PG: n})
    assert not any("99999" in c for c in X.columns)


def test_rotulos_dos_pontos_de_chuva_sao_unicos_para_nao_colidir_colunas() -> None:
    rotulos = list(PONTOS_CHUVA.values())
    assert len(rotulos) == len(set(rotulos))


def test_pontos_de_chuva_de_cada_alvo_estao_no_cadastro_de_rotulos() -> None:
    for cod in (*ALVOS, "DCSC-99999"):
        assert set(pontos_chuva(cod)) <= set(PONTOS_CHUVA)
    # rio dos Indios (ADR 0006): sem Boiteux (00021) e Vitor (00036); com Revolver e serras
    assert list(pontos_chuva(PG)) == [
        "DCSC-00043",
        "DCSC-00037",
        "DCSC-00015",
        "DCSC-00174",
        "DC-PEU-003",
        "DC-PEU-004",
        "DC-PEU-002",
    ]
    assert pontos_chuva(PG)["DCSC-00174"] == "revolver"  # o rotulo continua vindo de PONTOS_CHUVA
    antigos = {"DCSC-00043", "DCSC-00037", "DCSC-00021", "DCSC-00015", "DCSC-00036"}
    assert set(pontos_chuva("DCSC-99999")) == antigos  # estacao fora de ALVOS: conjunto padrao


def test_todo_ponto_de_chuva_e_todo_alvo_existem_no_seed() -> None:
    from common.seed import ESTACOES, ESTACOES_PDC

    cadastradas = {e[0] for e in ESTACOES + ESTACOES_PDC}
    assert set(PONTOS_CHUVA) <= cadastradas
    assert set(ALVOS) <= cadastradas
    for cfg in ALVOS.values():
        assert set(cfg.nivel_vizinhos) <= cadastradas


def test_revolver_nao_usa_boiteux_nem_ibirama_nem_interacoes() -> None:
    cfg = ALVOS[REVOLVER]
    assert cfg.interacoes is False and cfg.janela_dias is None
    assert set(cfg.nivel_vizinhos) == {PG}


# ---------- montar_features: valores ----------


def test_nivel_taxas_e_aceleracao_em_centimetros() -> None:
    nivel = serie([1.00, 1.10, 1.30, 1.60, 2.00])
    X = montar_features({PG: serie([0.0] * 5)}, {PG: nivel})
    assert X["nivel_m"].tolist() == [1.0, 1.1, 1.3, 1.6, 2.0]
    assert X["taxa_1h_cm"].iloc[1:].tolist() == pytest.approx([10.0, 20.0, 30.0, 40.0])
    assert X["taxa_3h_cm_h"].iloc[3:].tolist() == pytest.approx(
        [20.0, 30.0]
    )  # (1,6-1)/3 e (2-1,1)/3
    assert X["aceleracao_cm"].iloc[2:].tolist() == pytest.approx([10.0, 10.0, 10.0])
    assert X["taxa_1h_cm"].isna().iloc[0] and X["aceleracao_cm"].isna().iloc[:2].all()


def test_hora_do_dia_vira_seno_e_cosseno_ciclicos() -> None:
    n = serie([1.0] * 24)
    X = montar_features({PG: serie([0.0] * 24)}, {PG: n})
    assert X["hora_sen"].iloc[0] == pytest.approx(0.0) and X["hora_cos"].iloc[0] == 1.0
    assert X["hora_sen"].iloc[6] == pytest.approx(1.0)
    assert X["hora_cos"].iloc[12] == pytest.approx(-1.0)
    assert (X["hora_sen"] ** 2 + X["hora_cos"] ** 2).sub(1).abs().max() < 1e-12


def test_todas_as_janelas_de_cada_ponto_presente_e_nenhuma_dos_ausentes() -> None:
    n = serie([1.0] * 200)
    X = montar_features(
        {PG: serie([0.0] * 200), "DC-PEU-002": serie([1.0] * 200)}, {PG: n, REVOLVER: n}, REVOLVER
    )
    for j in JANELAS_CHUVA_H:
        assert f"chuva_local_{j}h" in X.columns and f"chuva_serra_mirador_{j}h" in X.columns
    assert not [c for c in X.columns if "emma" in c or "serra_vencida" in c]


def test_ponto_de_outro_alvo_nao_vira_coluna_do_pg() -> None:
    """Boiteux e Vitor nao sao pontos do PG (ADR 0006), mesmo presentes nos dados."""
    n = serie([1.0] * 200)
    chuva = {
        PG: serie([0.0] * 200),
        "DCSC-00021": serie([1.0] * 200),
        "DCSC-00036": serie([2.0] * 200),
        "DC-PEU-002": serie([1.0] * 200),
        REVOLVER: serie([2.0] * 200),
    }
    X = montar_features(chuva, {PG: n})
    assert not [c for c in X.columns if "boiteux" in c or "vitor" in c]
    assert "chuva_serra_mirador_6h" in X.columns and "chuva_revolver_6h" in X.columns


def test_interacoes_sao_o_produto_das_variaveis_de_origem_fora_de_alvos() -> None:
    """As interacoes explicitas so existem para estacao fora de ALVOS (o PG deixou de te-las)."""
    n = serie(list(np.linspace(1, 2, 60)))
    chuva = {
        PG: serie([1.0] * 60),
        "DCSC-00037": serie([2.0] * 60),
        "DCSC-00021": serie([3.0] * 60),
    }
    nivel = {"DCSC-99999": n, "DCSC-00021": n, "DCSC-00020": n * 2}
    X = montar_features(chuva, nivel, alvo="DCSC-99999")
    assert X["emma_x_boiteux_6h"].iloc[-1] == pytest.approx(12.0 * 18.0)
    assert X["ibirama_x_chuva_local_3h"].iloc[-1] == pytest.approx(2.0 * n.iloc[-1] * 3.0)


def test_pg_nao_tem_interacoes_nem_vizinhos_de_nivel_mesmo_com_todos_os_dados() -> None:
    n = serie(list(np.linspace(1, 2, 60)))
    chuva = {c: serie([1.0] * 60) for c in PONTOS_CHUVA}
    X = montar_features(chuva, {PG: n, "DCSC-00021": n, "DCSC-00020": n * 2})
    assert ALVOS[PG].interacoes is False and ALVOS[PG].janela_dias is None
    assert ALVOS[PG].nivel_vizinhos == {}
    assert "emma_x_boiteux_6h" not in X.columns and "ibirama_x_chuva_local_3h" not in X.columns
    assert not [c for c in X.columns if "ibirama" in c or "boiteux" in c or "vitor" in c]


def test_novas_variaveis_de_tendencia_e_faixa_das_ultimas_24h() -> None:
    n = 60
    nivel = serie([1.0 + 0.05 * i for i in range(n)])  # sobe 5 cm por hora
    X = montar_features({PG: serie([0.0] * n)}, {PG: nivel})
    assert X["taxa_6h_cm_h"].iloc[6:].tolist() == pytest.approx([5.0] * (n - 6))
    assert X["taxa_24h_cm_h"].iloc[24:].tolist() == pytest.approx([5.0] * (n - 24))
    assert X["taxa_6h_cm_h"].iloc[:6].isna().all() and X["taxa_24h_cm_h"].iloc[:24].isna().all()
    # minimo/maximo das ultimas 24 h INCLUINDO a hora t, e so com >= 18 horas de dado
    assert X["nivel_min_24h_m"].iloc[:17].isna().all() and not np.isnan(
        X["nivel_min_24h_m"].iloc[17]
    )
    assert X["nivel_min_24h_m"].iloc[40] == pytest.approx(nivel.iloc[17])  # janela [17, 40]
    assert X["nivel_max_24h_m"].iloc[40] == pytest.approx(nivel.iloc[40])


def test_novas_variaveis_de_nivel_nao_enxergam_o_futuro() -> None:
    rng = np.random.default_rng(8)
    n = 24 * 6
    nivel = pd.Series(rng.normal(2, 0.3, n), horas(n))
    chuva = {PG: pd.Series(rng.gamma(1.0, 2.0, n), horas(n))}
    t = 24 * 4
    completo = montar_features(chuva, {PG: nivel})
    cortado = montar_features({PG: chuva[PG].iloc[: t + 1]}, {PG: nivel.iloc[: t + 1]})
    novas = ["taxa_6h_cm_h", "taxa_24h_cm_h", "nivel_min_24h_m", "nivel_max_24h_m"]
    pd.testing.assert_series_equal(
        completo.iloc[t][novas], cortado.iloc[t][novas], check_names=False
    )
    adulterado = nivel.copy()
    adulterado.iloc[t + 1 :] = 99.0
    futuro = montar_features(chuva, {PG: adulterado})
    pd.testing.assert_series_equal(
        completo.iloc[t][novas], futuro.iloc[t][novas], check_names=False
    )


def test_interacoes_nao_existem_no_revolver_mesmo_com_todos_os_dados() -> None:
    n = serie(list(np.linspace(1, 2, 60)))
    chuva = {c: serie([1.0] * 60) for c in PONTOS_CHUVA}
    nivel = {PG: n, REVOLVER: n, "DCSC-00021": n, "DCSC-00020": n}
    X = montar_features(chuva, nivel, alvo=REVOLVER)
    assert "emma_x_boiteux_6h" not in X.columns
    assert "ibirama_x_chuva_local_3h" not in X.columns
    assert "nivel_ibirama_m" not in X.columns and "nivel_boiteux_m" not in X.columns


def test_features_do_revolver_nao_enxergam_o_futuro() -> None:
    rng = np.random.default_rng(5)
    n = 24 * 15
    chuva = {c: pd.Series(rng.gamma(1.0, 2.0, n), horas(n)) for c in PONTOS_CHUVA}
    nivel = {
        PG: pd.Series(rng.normal(2, 0.1, n), horas(n)),
        REVOLVER: pd.Series(rng.normal(1, 0.1, n), horas(n)),
    }
    t = 24 * 10
    completo = montar_features(chuva, nivel, alvo=REVOLVER)
    cortado = montar_features(
        {k: v.iloc[: t + 1] for k, v in chuva.items()},
        {k: v.iloc[: t + 1] for k, v in nivel.items()},
        alvo=REVOLVER,
    )
    pd.testing.assert_series_equal(completo.iloc[t], cortado.iloc[t], check_names=False)
    adulterado = {k: v.copy() for k, v in nivel.items()}
    for v in adulterado.values():
        v.iloc[t + 1 :] = 99.0
    pd.testing.assert_series_equal(
        completo.iloc[t],
        montar_features(chuva, adulterado, alvo=REVOLVER).iloc[t],
        check_names=False,
    )


def test_nivel_do_alvo_ausente_nos_dados_levanta_keyerror() -> None:
    with pytest.raises(KeyError):
        montar_features({PG: serie([0.0] * 10)}, {"DCSC-00021": serie([1.0] * 10)})


# ---------- alvo ----------


def test_alvo_deslocado_em_centimetros_e_ultimas_h_horas_sem_resposta() -> None:
    nivel = serie([1.0, 1.5, 1.2, 2.0, 2.0])
    y = alvo_deslocado(nivel, 3)
    assert y.iloc[:2].tolist() == pytest.approx([100.0, 50.0])
    assert y.iloc[2:].isna().all()


def test_alvo_com_buraco_no_nivel_futuro_fica_nan_e_nao_zero() -> None:
    nivel = serie([1.0, 1.0, np.nan, 1.0])
    y = alvo_deslocado(nivel, 2)
    assert np.isnan(y.iloc[0]) and y.iloc[1] == pytest.approx(0.0)


def test_alvo_de_horizonte_zero_e_sempre_zero() -> None:
    assert alvo_deslocado(serie([1.0, 2.0, 3.0]), 0).tolist() == [0.0, 0.0, 0.0]
