import numpy as np
import pandas as pd
import pytest

from modelo.features import alvo_deslocado, chuva_acumulada, montar_features
from modelo.treino import avaliar_horizonte, preparar


def idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-07-01", periods=n, freq="1h", tz="UTC")


def series_sinteticas(n: int = 24 * 90, atraso: int = 2, semente: int = 1):
    """Chuva frequente (30% das horas) que sobe o nivel `atraso` horas depois.

    O gradient boosting minimiza o erro ABSOLUTO: com chuva rara (8% das horas) ele aprende a
    mediana (variacao ~0) e empata com a persistencia. Aqui a chuva e comum o bastante para a
    relacao ser o padrao tipico, como nas semanas chuvosas dos dados reais.
    """
    rng = np.random.default_rng(semente)
    chuva = pd.Series(np.where(rng.random(n) < 0.3, rng.gamma(2.0, 3.0, n), 0.0), idx(n))
    resposta = np.zeros(n)
    resposta[atraso:] = chuva.to_numpy()[: n - atraso] * 0.03  # m por hora
    nivel = pd.Series(1.0 + np.cumsum(resposta), idx(n))
    return chuva, nivel


def feats(chuva: pd.Series, nivel: pd.Series) -> pd.DataFrame:
    return montar_features(
        {"DCSC-00043": chuva, "DCSC-00037": chuva.shift(1).fillna(0)},
        {"DCSC-00043": nivel, "DCSC-00021": nivel * 1.1, "DCSC-00020": nivel * 0.9},
    )


def test_features_nao_enxergam_o_futuro() -> None:
    """As variaveis de t nao mudam se o futuro for apagado ou alterado."""
    chuva, nivel = series_sinteticas(24 * 20)
    completo = feats(chuva, nivel)
    t = 24 * 15
    cortado = feats(chuva.iloc[: t + 1], nivel.iloc[: t + 1])
    pd.testing.assert_series_equal(completo.iloc[t], cortado.iloc[t], check_names=False)
    # e corromper o futuro tambem nao muda o presente
    adulterado = nivel.copy()
    adulterado.iloc[t + 1 :] = 99.0
    f2 = feats(chuva.iloc[:], adulterado)
    pd.testing.assert_series_equal(completo.iloc[t], f2.iloc[t], check_names=False)


def test_alvo_olha_para_frente_e_so_ele() -> None:
    nivel = pd.Series([1.0, 1.1, 1.3, 1.2], idx(4))
    y = alvo_deslocado(nivel, 2)
    assert y.iloc[0] == pytest.approx(30.0) and y.iloc[1] == pytest.approx(10.0)
    assert np.isnan(y.iloc[2]) and np.isnan(y.iloc[3])


def test_janela_de_chuva_com_falha_curta_e_nan_e_com_falha_longa_e_reescalada() -> None:
    chuva = pd.Series(1.0, idx(200))
    chuva.iloc[100] = np.nan
    assert np.isnan(chuva_acumulada(chuva, 6).iloc[102])  # janela curta com falha: desconhecida
    longa = chuva_acumulada(chuva, 72).iloc[150]  # 72 h com 1 falha (1,4%): tolera e reescala
    assert abs(longa - 72.0) < 1e-6


def test_uma_hora_faltando_nao_zera_a_janela_de_24h() -> None:
    chuva = pd.Series(1.0, idx(200))
    chuva.iloc[100] = np.nan
    assert abs(chuva_acumulada(chuva, 24).iloc[110] - 24.0) < 1e-6  # tolera e reescala
    assert abs(chuva_acumulada(chuva, 12).iloc[105] - 12.0) < 1e-6
    chuva.iloc[101:110] = np.nan  # varias horas sem dado: continua desconhecida
    assert np.isnan(chuva_acumulada(chuva, 24).iloc[110])


def test_hora_sem_cobertura_nao_vira_zero() -> None:
    chuva = pd.Series(0.0, idx(50))
    chuva.iloc[20:30] = np.nan
    f = chuva_acumulada(chuva, 3)
    assert f.iloc[25:30].isna().all()


def test_modelo_aprende_relacao_real_e_vence_a_persistencia() -> None:
    chuva, nivel = series_sinteticas(24 * 120)
    X = feats(chuva, nivel)
    r = avaliar_horizonte(X, alvo_deslocado(nivel, 3), 3)
    assert r.rmse_cm is not None and r.rmse_persistencia_cm is not None
    assert r.rmse_cm < r.rmse_persistencia_cm
    assert r.publicar, r.motivo


def test_ruido_puro_nao_e_publicado() -> None:
    rng = np.random.default_rng(9)
    n = 24 * 120
    chuva = pd.Series(np.where(rng.random(n) < 0.08, rng.gamma(2.0, 3.0, n), 0.0), idx(n))
    nivel = pd.Series(1.5 + np.cumsum(rng.normal(0, 0.01, n)), idx(n)).clip(lower=0.5)
    r = avaliar_horizonte(feats(chuva, nivel), alvo_deslocado(nivel, 6), 6)
    assert not r.publicar


def test_poucos_dias_nunca_publica_mesmo_se_o_modelo_for_bom() -> None:
    chuva, nivel = series_sinteticas(24 * 40)  # so 40 dias
    r = avaliar_horizonte(feats(chuva, nivel), alvo_deslocado(nivel, 3), 3)
    assert not r.publicar and "mínimo para publicar" in r.motivo


def test_poucas_linhas_devolve_motivo_sem_quebrar() -> None:
    chuva, nivel = series_sinteticas(24 * 5)
    r = avaliar_horizonte(feats(chuva, nivel), alvo_deslocado(nivel, 3), 3)
    assert not r.publicar and "Poucos dados" in r.motivo


def test_preparar_so_exige_alvo_e_obrigatorias_e_mantem_a_ordem() -> None:
    chuva, nivel = series_sinteticas(24 * 10)
    X = feats(chuva, nivel)
    Xc, yc = preparar(X, alvo_deslocado(nivel, 3))
    assert not Xc[["nivel_m", "taxa_1h_cm", "taxa_3h_cm_h"]].isna().any().any()
    assert not yc.isna().any() and Xc.index.is_monotonic_increasing
    # as janelas longas de chuva ainda nao fecham nas primeiras horas: a linha FICA, com NaN
    assert Xc["chuva_local_168h"].isna().any() and len(Xc) > len(X.dropna())


# ---------- inferencia ----------


def _artefato_treinado():
    from modelo.treino import avaliar_horizonte

    chuva, nivel = series_sinteticas(24 * 120)
    X = feats(chuva, nivel)
    r = avaliar_horizonte(X, alvo_deslocado(nivel, 3), 3)
    assert r.pipeline is not None
    return {"pipeline": r.pipeline, "colunas": r.colunas, "faixa_treino": r.faixa_treino}, X


def test_previsao_sobe_quando_o_cenario_tem_muita_chuva() -> None:
    from modelo.inferencia import aplicar_cenario, prever_variacao_cm

    art, X = _artefato_treinado()
    linha = X.dropna().iloc[-1]
    seco = aplicar_cenario(linha, {"DCSC-00043": 0.0, "DCSC-00037": 0.0}, 6)
    chuvoso = aplicar_cenario(linha, {"DCSC-00043": 25.0, "DCSC-00037": 25.0}, 6)
    assert prever_variacao_cm(art, chuvoso) > prever_variacao_cm(art, seco)


def test_cenario_nunca_reduz_a_chuva_ja_acumulada_nas_janelas_longas() -> None:
    from modelo.inferencia import aplicar_cenario

    _, X = _artefato_treinado()
    linha = X.dropna().iloc[-1].copy()
    linha["chuva_local_72h"] = 50.0
    nova = aplicar_cenario(linha, {"DCSC-00043": 1.0}, 3)
    assert nova["chuva_local_72h"] == 50.0  # o que ja choveu continua valendo
    assert nova["chuva_local_1h"] == pytest.approx(1.0 / 3)  # fracao proporcional da janela


def test_extrapolacao_e_sinalizada_fora_da_faixa_do_treino() -> None:
    from modelo.inferencia import aplicar_cenario, extrapola

    art, X = _artefato_treinado()
    linha = X.dropna().iloc[-10]  # uma hora de dentro do treino (as ultimas nao tem alvo)
    assert extrapola(art, linha) == []
    enorme = aplicar_cenario(linha, {"DCSC-00043": 5000.0}, 1)
    assert "chuva_local_1h" in extrapola(art, enorme)
