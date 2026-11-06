"""Chuva horaria: incremento onde ha cobertura, h001 (fechando a hora) onde nao ha."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from modelo import dados
from modelo.dados import (
    FONTES_CHUVA_MEDIDA,
    chuva_horaria,
    combinar_chuva,
    horaria_h001,
    horaria_media,
    horaria_soma,
    remover_picos_h001,
    uma_leitura_por_intervalo,
)

H0 = pd.Timestamp("2026-10-01 00:00", tz="UTC")


def leituras(pares: list[tuple[str, float]]) -> pd.Series:
    idx = pd.DatetimeIndex([pd.Timestamp(f"2026-10-01 {hm}", tz="UTC") for hm, _ in pares])
    return pd.Series([v for _, v in pares], idx, dtype=float)


def grade_5min(inicio: str, fim: str, valor: float) -> pd.Series:
    idx = pd.date_range(f"2026-10-01 {inicio}", f"2026-10-01 {fim}", freq="5min", tz="UTC")
    return pd.Series(valor, idx)


# ---------- h001 -> chuva da hora ----------


def test_a_hora_h_usa_a_leitura_que_fecha_a_hora() -> None:
    # h001 as 01:00 = chuva de [00:00, 01:00) -> hora rotulada 00:00
    r = horaria_h001(leituras([("00:00", 1.0), ("01:00", 4.0), ("02:00", 7.0)]))
    assert r[H0] == 4.0
    assert r[H0 + pd.Timedelta(hours=1)] == 7.0
    assert r[H0 - pd.Timedelta(hours=1)] == 1.0


def test_tolerancia_5_min_antes_e_1_min_depois() -> None:
    def hora0(hm: str) -> float:
        return horaria_h001(leituras([(hm, 3.0)])).get(H0, np.nan)

    assert hora0("00:55") == 3.0  # 5 min antes: ainda descreve quase a mesma hora
    assert hora0("01:00") == 3.0
    assert hora0("01:01") == 3.0  # jitter de carimbo
    assert np.isnan(hora0("00:54"))  # mais de 5 min antes: janela deslocada demais
    assert np.isnan(hora0("01:02"))  # depois da folga: seria futuro


def test_prefere_a_leitura_mais_proxima_do_fim_da_hora() -> None:
    r = horaria_h001(leituras([("00:55", 1.0), ("01:00", 2.0)]))
    assert r[H0] == 2.0
    r = horaria_h001(leituras([("00:55", 1.0)]))  # a de :00 falhou
    assert r[H0] == 1.0


def test_sem_leitura_na_tolerancia_e_nan_nunca_zero() -> None:
    r = horaria_h001(leituras([("00:00", 1.0), ("03:00", 2.0)]))
    assert r.notna().sum() == 2  # horas 23:00 (leitura das 00:00) e 02:00 (leitura das 03:00)
    assert r[H0 : H0 + pd.Timedelta(hours=1)].isna().all()  # 00:00 e 01:00 sem leitura
    assert horaria_h001(pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))).empty


def test_nao_vaza_futuro_para_alem_da_tolerancia() -> None:
    """A hora H nao muda se tudo depois de H+1h+1min for apagado ou adulterado."""
    base = grade_5min("00:00", "04:00", 1.0)
    base.loc[pd.Timestamp("2026-10-01 01:00", tz="UTC")] = 5.0
    limite = pd.Timestamp("2026-10-01 01:01", tz="UTC")
    cortada = base[base.index <= limite]
    adulterada = base.copy()
    adulterada[adulterada.index > limite] = 99.0
    esperado = horaria_h001(base)[H0]
    assert esperado == 5.0
    assert horaria_h001(cortada)[H0] == esperado
    assert horaria_h001(adulterada)[H0] == esperado


def test_leituras_duplicadas_no_mesmo_instante_viram_media() -> None:
    idx = pd.DatetimeIndex([pd.Timestamp("2026-10-01 01:00", tz="UTC")] * 2)
    r = horaria_h001(pd.Series([2.0, 4.0], idx))
    assert r[H0] == 3.0


def test_respeita_inicio_e_fim_dos_rotulos() -> None:
    bruta = grade_5min("00:00", "06:00", 1.0)
    r = horaria_h001(bruta, H0 + pd.Timedelta(hours=1), H0 + pd.Timedelta(hours=4))
    assert list(r.index) == list(pd.date_range(H0 + pd.Timedelta(hours=1), periods=3, freq="1h"))


# ---------- pico espurio ----------


def test_pico_isolado_em_serie_de_5_min_e_descartado() -> None:
    bruta = grade_5min("00:00", "01:00", 2.0)
    bruta.iloc[6] = 45.0  # 43 mm acima da leitura anterior, em 5 min: impossivel
    limpa = remover_picos_h001(bruta)
    assert len(limpa) == len(bruta) - 1 and 45.0 not in limpa.to_numpy()


def test_teto_absoluto_descarta_mesmo_sem_vizinhas() -> None:
    bruta = leituras([("00:00", 1.0), ("01:00", 248.0), ("02:00", 1.0)])
    assert remover_picos_h001(bruta).tolist() == [1.0, 1.0]


def test_subida_real_gradual_nao_e_tocada() -> None:
    idx = pd.date_range("2026-10-01 00:00", periods=13, freq="5min", tz="UTC")
    rampa = pd.Series(np.linspace(0, 60, 13), idx)  # 5 mm por passo: chuva forte, mas fisica
    assert len(remover_picos_h001(rampa)) == 13


def test_salto_grande_em_serie_horaria_nao_e_julgado() -> None:
    bruta = leituras([("00:00", 0.0), ("01:00", 60.0), ("02:00", 0.0)])  # sem vizinha em 10 min
    assert remover_picos_h001(bruta).tolist() == [0.0, 60.0, 0.0]


def test_pico_removido_cai_na_leitura_anterior_dentro_da_tolerancia() -> None:
    bruta = grade_5min("00:00", "02:00", 2.0)
    bruta[pd.Timestamp("2026-10-01 01:00", tz="UTC")] = 80.0  # pico isolado na leitura exata
    assert horaria_h001(bruta)[H0] == 2.0  # usa a das 00:55


# ---------- combinacao incremento / h001 ----------


def serie_h(valores: list[float], inicio: str = "2026-10-01 00:00") -> pd.Series:
    return pd.Series(valores, pd.date_range(inicio, periods=len(valores), freq="1h", tz="UTC"))


def test_com_cobertura_de_incremento_o_incremento_vale() -> None:
    r = combinar_chuva(serie_h([1.0, 2.0]), serie_h([9.0, 9.0]))
    assert r.tolist() == [1.0, 2.0]


def test_sem_cobertura_de_incremento_usa_h001() -> None:
    r = combinar_chuva(serie_h([1.0, np.nan, 3.0]), serie_h([9.0, 4.0, 9.0]))
    assert r.tolist() == [1.0, 4.0, 3.0]


def test_sem_nada_e_nan_e_o_indice_continua_regular() -> None:
    r = combinar_chuva(serie_h([1.0]), serie_h([5.0], "2026-10-01 04:00"))
    assert len(r) == 5 and r.iloc[1:4].isna().all()
    assert r.index.freq is not None or (np.diff(r.index.view("i8")) == 3_600_000_000_000).all()
    assert combinar_chuva(serie_h([]), serie_h([])).empty


def test_so_h001_ou_so_incremento() -> None:
    assert combinar_chuva(serie_h([]), serie_h([2.0, 3.0])).tolist() == [2.0, 3.0]
    assert combinar_chuva(serie_h([2.0, 3.0]), serie_h([])).tolist() == [2.0, 3.0]


def test_incremento_com_cobertura_baixa_cai_para_o_h001() -> None:
    """Fluxo completo: 8 de 12 incrementos (< 9) na hora 00:00 nao servem; vale o h001."""
    idx = pd.date_range("2026-10-01 00:00", periods=8, freq="5min", tz="UTC")
    incr = horaria_soma(pd.Series(1.0, idx), dados.MIN_LEITURAS_CHUVA)
    assert np.isnan(incr[H0])
    r = combinar_chuva(incr, horaria_h001(leituras([("01:00", 6.5)])))
    assert r[H0] == 6.5


# ---------- chuva_horaria (com a consulta ao banco substituida) ----------


class Banco:
    """Substitui `_serie_bruta`: devolve a serie pedida, cortada pela janela, e anota as fontes."""

    def __init__(self, series: dict[str, pd.Series]) -> None:
        self.series = series
        self.fontes: dict[str, tuple[str, ...] | None] = {}

    def __call__(self, s, codigo, variavel, inicio, fim, fontes=None) -> pd.Series:
        self.fontes[variavel] = fontes
        serie = self.series.get(variavel)
        if serie is None:
            return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
        return serie[(serie.index >= inicio) & (serie.index < fim)]


def test_chuva_horaria_mistura_incremento_e_h001_so_de_fonte_medida(monkeypatch) -> None:
    incr = grade_5min("00:00", "00:55", 0.5)  # hora 00:00 completa: 12 x 0,5 = 6 mm
    h001 = grade_5min("00:00", "04:00", 1.0)  # sai 1 mm/h onde so ha h001
    banco = Banco({"chuva_acumulada_mm": incr, "chuva_h001_mm": h001})
    monkeypatch.setattr(dados, "_serie_bruta", banco)
    fim = datetime(2026, 10, 1, 3, 0, tzinfo=UTC)
    r = chuva_horaria(None, "X", H0.to_pydatetime(), fim)
    assert r[H0] == pytest.approx(6.0)  # incremento manda
    assert r[H0 + pd.Timedelta(hours=1)] == 1.0 and r[H0 + pd.Timedelta(hours=2)] == 1.0
    assert r.index.max() == H0 + pd.Timedelta(hours=2)  # rotulos so em [inicio, fim)
    assert banco.fontes["chuva_h001_mm"] == FONTES_CHUVA_MEDIDA
    assert banco.fontes["chuva_acumulada_mm"] is None


def test_chuva_horaria_nao_usa_reanalise_nem_previsao() -> None:
    assert not any("openmeteo" in f for f in FONTES_CHUVA_MEDIDA)
    assert {"dcsc_graphql", "dcsc_rest", "pdc_municipal"} == set(FONTES_CHUVA_MEDIDA)


def test_chuva_horaria_sem_nada_e_vazia(monkeypatch) -> None:
    monkeypatch.setattr(dados, "_serie_bruta", Banco({}))
    fim = datetime(2026, 10, 2, tzinfo=UTC)
    assert chuva_horaria(None, "X", H0.to_pydatetime(), fim).empty


def test_ultima_hora_da_janela_pede_a_leitura_que_so_existe_em_fim(monkeypatch) -> None:
    """A hora [fim-1h, fim) fecha em `fim`: a consulta do h001 precisa ir ate fim+1min."""
    h001 = leituras([("03:00", 8.0)])
    monkeypatch.setattr(dados, "_serie_bruta", Banco({"chuva_h001_mm": h001}))
    fim = datetime(2026, 10, 1, 3, 0, tzinfo=UTC)
    r = chuva_horaria(None, "X", fim - timedelta(hours=1), fim)
    assert r.tolist() == [8.0] and r.index[0] == H0 + pd.Timedelta(hours=2)


def test_duas_fontes_com_instantes_defasados_dao_uma_leitura_por_hora_sem_somar() -> None:
    """pdc_municipal (:00:00) e dcsc_graphql (:00:40) quase iguais: vale uma so, nunca a soma."""
    a = grade_5min("00:00", "03:00", 4.0)
    b = a.copy()
    b.index = b.index + pd.Timedelta(seconds=40)
    b[:] = 4.1
    r = horaria_h001(pd.concat([a, b]).sort_index())
    assert r.notna().all() and r.between(4.0, 4.1).all()
    # nivel: a media de leituras das duas fontes nao dobra o valor
    nivel = dados.horaria_media(pd.concat([a, b]).sort_index(), dados.MIN_LEITURAS_NIVEL)
    assert nivel.dropna().between(4.0, 4.1).all()


# ---------- filtro de pico: causal (so olha o passado) ----------


def serie_com_picos(semente: int = 0, n: int = 160) -> pd.Series:
    """Serie de 5 min com chuva forte real (subida gradual), picos isolados e lacunas."""
    rng = np.random.default_rng(semente)
    idx = pd.date_range("2026-10-01 00:00", periods=n, freq="5min", tz="UTC")
    v = np.cumsum(rng.normal(0.0, 1.5, n)).clip(0, 60)
    for i in rng.choice(n, 8, replace=False):
        v[i] += rng.uniform(35, 120)  # picos nao fisicos
    s = pd.Series(v, idx)
    return s.drop(s.index[rng.choice(n, 12, replace=False)])  # lacunas de 5 a 15 min


@pytest.mark.parametrize("semente", range(6))
def test_filtro_de_pico_e_causal_serie_cortada_igual_a_completa_cortada(semente: int) -> None:
    """f(serie[:t]) == f(serie)[:t] para qualquer t: treino e inferencia filtram igual."""
    s = serie_com_picos(semente)
    completa = remover_picos_h001(s)
    for t in range(1, len(s) + 1):
        corte = s.iloc[:t]
        esperado = completa[completa.index <= corte.index[-1]]
        pd.testing.assert_series_equal(remover_picos_h001(corte), esperado)


def test_filtro_nao_usa_a_leitura_seguinte() -> None:
    """Trocar o que vem DEPOIS de uma leitura nao muda se ela e mantida ou descartada."""
    base = grade_5min("00:00", "01:00", 2.0)
    base.iloc[6] = 45.0
    a, b = base.copy(), base.copy()
    a.iloc[7:] = 0.0
    b.iloc[7:] = 80.0
    for outra in (a, b):
        assert outra.index[6] not in remover_picos_h001(outra).index  # pico segue descartado
    # e um degrau legitimo (sobe e fica) perde so a primeira leitura do degrau
    degrau = grade_5min("00:00", "00:40", 1.0)
    degrau.iloc[4:] = 50.0
    limpo = remover_picos_h001(degrau)
    assert degrau.index[4] not in limpo.index and degrau.index[5] in limpo.index
    assert len(limpo) == len(degrau) - 1


def test_subida_rapida_legitima_de_chuva_forte_passa() -> None:
    """Chuva forte real: 10 mm por passo de 5 min (120 mm/h) comecando do zero nao e tocada."""
    idx = pd.date_range("2026-10-01 00:00", periods=8, freq="5min", tz="UTC")
    forte = pd.Series([0, 10, 20, 30, 40, 50, 60, 70], idx, dtype=float)
    assert len(remover_picos_h001(forte)) == 8


def test_salto_apos_lacuna_maior_que_10_min_nao_e_julgado() -> None:
    bruta = leituras([("00:00", 1.0), ("00:05", 1.0), ("00:20", 60.0)])  # anterior a 15 min
    assert remover_picos_h001(bruta).tolist() == [1.0, 1.0, 60.0]


def test_pico_depois_de_outro_pico_e_comparado_ao_passado_bruto() -> None:
    bruta = grade_5min("00:00", "00:30", 1.0)
    bruta.iloc[3] = 100.0
    bruta.iloc[4] = 101.0  # anterior bruta (100) e alta: nao e salto novo; documenta o compromisso
    limpa = remover_picos_h001(bruta)
    assert bruta.index[3] not in limpa.index and bruta.index[4] in limpa.index


# ---------- duas fontes no mesmo ponto: um instante conta uma vez ----------


def duas_fontes(valor_a: float, valor_b: float, n: int = 3) -> pd.Series:
    """n instantes de 5 min gravados por duas fontes com 40 s de diferenca."""
    a = grade_5min("00:00", f"00:{5 * (n - 1):02d}", valor_a)
    b = a.copy()
    b.index = b.index + pd.Timedelta(seconds=40)
    b[:] = valor_b
    return pd.concat([a, b]).sort_index()


def test_tres_instantes_em_duas_fontes_nao_valem_seis_leituras_de_nivel() -> None:
    nivel = horaria_media(duas_fontes(2.0, 2.2), dados.MIN_LEITURAS_NIVEL)
    assert nivel.isna().all()  # 3 instantes distintos < 6 (antes: 6 leituras brutas passavam)


def test_seis_instantes_em_duas_fontes_passam_e_a_media_nao_pesa_uma_fonte() -> None:
    nivel = horaria_media(duas_fontes(2.0, 2.2, n=6), dados.MIN_LEITURAS_NIVEL)
    assert nivel.iloc[0] == pytest.approx(2.1)


def test_leitura_extra_no_mesmo_intervalo_so_pesa_um_instante() -> None:
    a = grade_5min("00:00", "00:55", 1.0)  # 12 instantes
    b = pd.Series(3.0, [pd.Timestamp("2026-10-01 00:00:30", tz="UTC")])  # mesmo intervalo das 00:00
    nivel = horaria_media(pd.concat([a, b]).sort_index(), dados.MIN_LEITURAS_NIVEL)
    # o intervalo das 00:00 vira a media (1 e 3 = 2); os outros 11 ficam em 1
    assert nivel.iloc[0] == pytest.approx((11 * 1.0 + 2.0) / 12)


def test_chuva_incremento_nao_dobra_nem_infla_a_cobertura_com_duas_fontes() -> None:
    # 5 instantes (< 9 de 12) em duas fontes: 10 leituras brutas passariam do minimo
    assert horaria_soma(duas_fontes(1.0, 1.0, n=5), dados.MIN_LEITURAS_CHUVA).isna().all()
    # 10 instantes em duas fontes: soma de 10 incrementos de 1 mm, nao de 20
    assert horaria_soma(duas_fontes(1.0, 1.0, n=10), dados.MIN_LEITURAS_CHUVA).iloc[0] == 10.0


def test_uma_fonte_em_cadencia_de_5_min_passa_inalterada() -> None:
    s = grade_5min("00:00", "00:55", 1.5)
    pd.testing.assert_series_equal(uma_leitura_por_intervalo(s), s, check_freq=False)
    assert horaria_soma(s, dados.MIN_LEITURAS_CHUVA).iloc[0] == pytest.approx(18.0)
