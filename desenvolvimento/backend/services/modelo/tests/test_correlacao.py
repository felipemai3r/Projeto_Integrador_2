import numpy as np
import pandas as pd
import pytest

from modelo.correlacao import (
    ResultadoPonto,
    ajustar_multiplicidade,
    analisar_ponto,
    chuva_em_janela,
    curva_de_correlacao,
    delta_nivel_cm,
    residuo_sem_chuva_local,
)
from modelo.dados import horaria_media, horaria_soma


def indice(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-08-01", periods=n, freq="1h", tz="UTC")


def cenario(atraso_h: int, n: int = 24 * 40, semente: int = 7, ruido: float = 0.2):
    """atraso_h negativo = o nivel sobe ANTES da chuva (causalidade invertida)."""
    """Chuva em pulsos esparsos; o nivel sobe `atraso_h` horas depois de cada pulso."""
    rng = np.random.default_rng(semente)
    chuva = np.where(rng.random(n) < 0.08, rng.gamma(2.0, 3.0, n), 0.0)
    resposta = np.zeros(n)
    if atraso_h >= 0:
        resposta[atraso_h:] = chuva[: n - atraso_h]
    else:
        resposta[: n + atraso_h] = chuva[-atraso_h:]
    delta = resposta * 2.0 + rng.normal(0, ruido, n)  # cm por hora
    nivel = 1.0 + np.cumsum(delta) / 100.0
    idx = indice(n)
    return pd.Series(chuva, idx), pd.Series(nivel, idx)


def test_encontra_a_defasagem_verdadeira() -> None:
    chuva, nivel = cenario(atraso_h=5)
    res = analisar_ponto("P", chuva, delta_nivel_cm(nivel), janela_h=1, repeticoes=200)
    assert res is not None
    assert res.melhor_defasagem_h == 5
    assert res.r > 0.4  # chuva tem ~92% de zeros: empates reduzem o r de postos
    assert res.p_valor is not None and res.p_valor < 0.01
    assert res.sinal_claro


def test_defasagem_muda_com_o_atraso() -> None:
    for atraso in (2, 9):
        chuva, nivel = cenario(atraso_h=atraso, semente=11)
        res = analisar_ponto("P", chuva, delta_nivel_cm(nivel), janela_h=1, repeticoes=30)
        assert res is not None
        assert res.melhor_defasagem_h == atraso


def test_ruido_puro_nao_vira_sinal_claro() -> None:
    rng = np.random.default_rng(3)
    n = 24 * 40
    idx = indice(n)
    chuva = pd.Series(np.where(rng.random(n) < 0.08, rng.gamma(2.0, 3.0, n), 0.0), idx)
    nivel = pd.Series(1.0 + np.cumsum(rng.normal(0, 0.3, n)) / 100.0, idx)
    res = analisar_ponto("P", chuva, delta_nivel_cm(nivel), janela_h=1, repeticoes=80)
    assert res is not None
    assert abs(res.r) < 0.25
    assert res.p_valor is not None and res.p_valor > 0.05
    assert not res.sinal_claro  # o acaso explica o melhor r entre as 36 defasagens


def test_nao_ha_defasagem_zero_ou_negativa() -> None:
    """A analise so olha o passado: a menor defasagem avaliada e 1 hora."""
    chuva, nivel = cenario(atraso_h=4)
    curva = curva_de_correlacao(chuva_em_janela(chuva, 1), delta_nivel_cm(nivel))
    assert min(p.defasagem_h for p in curva) == 1


def test_causalidade_invertida_nao_gera_sinal() -> None:
    """Nivel sobe 4 h ANTES da chuva: olhando so o passado, a chuva nao explica a subida."""
    chuva, nivel = cenario(atraso_h=-4)
    res = analisar_ponto("P", chuva, delta_nivel_cm(nivel), janela_h=1, repeticoes=100)
    assert res is not None
    assert not res.sinal_claro


def test_a_janela_de_chuva_usa_so_horas_passadas() -> None:
    chuva = pd.Series([0, 0, 10, 0, 0, 0.0], indice(6))
    janela = chuva_em_janela(chuva, 3)
    assert janela.iloc[2] == 10  # inclui a propria hora t e as 2 anteriores
    assert janela.iloc[1] != janela.iloc[1]  # NaN: nao ha 3 horas de historico
    assert janela.iloc[4] == 10  # hora 2 ainda esta na janela de 3 h que termina na hora 4
    assert janela.iloc[5] == 0  # saiu da janela: nada de futuro nem de passado distante


def test_hora_sem_cobertura_e_desconhecida_nao_e_zero() -> None:
    # 12 leituras de 5 min na hora 0 e apenas 2 na hora 1
    idx = pd.date_range("2026-08-01 00:00", periods=12, freq="5min", tz="UTC").append(
        pd.date_range("2026-08-01 01:00", periods=2, freq="5min", tz="UTC")
    )
    bruta = pd.Series([1.0] * 14, idx)
    soma = horaria_soma(bruta, minimo=9)
    assert soma.iloc[0] == 12.0
    assert np.isnan(soma.iloc[1])  # lacuna nao pode virar "hora sem chuva"
    media = horaria_media(pd.Series([2.0] * 14, idx), minimo=6)
    assert media.iloc[0] == 2.0 and np.isnan(media.iloc[1])


def test_poucos_dados_devolve_none() -> None:
    idx = indice(20)
    chuva = pd.Series(np.zeros(20), idx)
    nivel = pd.Series(np.linspace(1, 1.1, 20), idx)
    assert analisar_ponto("P", chuva, delta_nivel_cm(nivel), repeticoes=10) is None


def test_delta_em_centimetros() -> None:
    nivel = pd.Series([1.00, 1.05, 1.02], indice(3))
    d = delta_nivel_cm(nivel)
    assert np.isnan(d.iloc[0])
    assert d.iloc[1] == pytest.approx(5.0)
    assert d.iloc[2] == pytest.approx(-3.0)


def test_desconto_da_chuva_local_remove_o_efeito_de_um_ponto_colinear() -> None:
    """A montante cai a mesma chuva (colinear), mas so a chuva local move o nivel."""
    rng = np.random.default_rng(5)
    n = 24 * 40
    idx = indice(n)
    tempestade = np.where(rng.random(n) < 0.08, rng.gamma(2.0, 3.0, n), 0.0)
    local = pd.Series(tempestade * rng.uniform(0.7, 1.3, n), idx)
    montante = pd.Series(tempestade * rng.uniform(0.7, 1.3, n), idx)  # mesma tempestade
    resposta = np.zeros(n)
    resposta[1:] = local.to_numpy()[: n - 1]  # nivel responde so a chuva local, 1 h depois
    delta = pd.Series(resposta * 2.0 + rng.normal(0, 0.2, n), idx)

    bruto = analisar_ponto("M", montante, delta, janela_h=1, repeticoes=50)
    descontado = analisar_ponto(
        "M", montante, residuo_sem_chuva_local(delta, local), janela_h=1, repeticoes=100
    )
    assert bruto is not None and descontado is not None
    assert bruto.r > 0.25  # parece que o ponto a montante explica o rio...
    assert descontado.r < bruto.r / 2  # ...mas some quando se desconta a chuva local
    assert not descontado.sinal_claro


def test_residuo_sem_dados_suficientes_devolve_nan() -> None:
    idx = indice(10)
    r = residuo_sem_chuva_local(pd.Series(np.arange(10.0), idx), pd.Series(np.zeros(10), idx))
    assert r.isna().all()


def _res(ponto: str, expl: str, p: float | None) -> ResultadoPonto:
    return ResultadoPonto(
        ponto=ponto,
        explicativa=expl,
        janela_chuva_h=3,
        melhor_defasagem_h=1,
        r=0.2,
        ic_inf=0.1,
        ic_sup=0.3,
        p_valor=p,
        horas_validas=1000,
        curva=[],
    )


def test_bonferroni_corrige_pelo_numero_de_testes_de_cada_analise() -> None:
    rs = (
        [_res("A", "chuva_sem_local", 0.026)]
        + [_res(c, "chuva_sem_local", 0.2) for c in "BCD"]
        + [_res("E", "chuva_sem_local", 0.002), _res("F", "nivel", 0.02)]
    )
    aj = ajustar_multiplicidade(rs)
    assert aj[0].p_valor == pytest.approx(0.026 * 5)  # 5 testes na analise
    assert not aj[0].sinal_claro  # o p de 0,026 deixa de ser sinal: era esperado por acaso
    assert aj[4].p_valor == pytest.approx(0.01) and aj[4].sinal_claro
    assert aj[5].p_valor == pytest.approx(0.02)  # uma analise com 1 teste nao muda
    assert all(a.p_valor is None or a.p_valor <= 1 for a in aj)


def test_bonferroni_limita_a_um_e_preserva_none() -> None:
    aj = ajustar_multiplicidade([_res("A", "x", 0.9), _res("B", "x", 0.8), _res("C", "x", None)])
    assert aj[0].p_valor == 1.0 and aj[1].p_valor == 1.0 and aj[2].p_valor is None
