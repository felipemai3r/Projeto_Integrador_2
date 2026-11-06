"""Risco e tendencia: limiares inclusivos, escala completa, tolerancia de 7 min e fronteiras."""

from datetime import UTC, datetime, timedelta

import pytest
from common.enums import Faixa

from api.risco import (
    LIMITE_ESTAVEL_CM_H,
    ORDEM,
    TOLERANCIA_PONTO,
    _valor_em,
    classificar,
    taxa_e_aceleracao,
    tendencia,
)

T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
# limiares do Revolver (DCSC-00174)
REV = {Faixa.ATENCAO: 2.5, Faixa.ALERTA: 3.0, Faixa.ALERTA_ALTO: 3.5}


def test_ordem_da_escala_e_a_da_defesa_civil_de_sc() -> None:
    assert ORDEM == [Faixa.NORMAL, Faixa.ATENCAO, Faixa.ALERTA, Faixa.ALERTA_ALTO, Faixa.EXTREMO]
    assert timedelta(minutes=7) == TOLERANCIA_PONTO and LIMITE_ESTAVEL_CM_H == 2.0


# ---------- classificar ----------


@pytest.mark.parametrize(
    ("nivel", "faixa"),
    [
        (0.0, Faixa.NORMAL),
        (2.499, Faixa.NORMAL),
        (2.5, Faixa.ATENCAO),
        (2.999, Faixa.ATENCAO),
        (3.0, Faixa.ALERTA),
        (3.499, Faixa.ALERTA),
        (3.5, Faixa.ALERTA_ALTO),
        (50.0, Faixa.ALERTA_ALTO),
    ],
)
def test_revolver_usa_os_proprios_limiares_e_nao_os_do_rio_dos_indios(
    nivel: float, faixa: Faixa
) -> None:
    assert classificar(nivel, REV) == faixa


def test_o_mesmo_nivel_cai_em_faixas_diferentes_conforme_a_estacao() -> None:
    pg = {Faixa.ATENCAO: 4.0, Faixa.ALERTA: 4.5, Faixa.ALERTA_ALTO: 5.5}
    assert classificar(3.2, pg) == Faixa.NORMAL
    assert classificar(3.2, REV) == Faixa.ALERTA


def test_sem_nenhum_limiar_cadastrado_tudo_e_normal() -> None:
    assert classificar(30.0, {}) == Faixa.NORMAL


def test_nivel_negativo_e_normal() -> None:
    assert classificar(-1.0, REV) == Faixa.NORMAL


def test_extremo_so_com_limiar_e_acima_dele() -> None:
    lim = {**REV, Faixa.EXTREMO: 4.5}
    assert classificar(4.499, lim) == Faixa.ALERTA_ALTO
    assert classificar(4.5, lim) == Faixa.EXTREMO


def test_so_extremo_cadastrado_e_nada_mais() -> None:
    assert classificar(9.0, {Faixa.EXTREMO: 7.0}) == Faixa.EXTREMO
    assert classificar(6.0, {Faixa.EXTREMO: 7.0}) == Faixa.NORMAL


def test_faixa_normal_no_dicionario_de_limiares_e_ignorada() -> None:
    assert classificar(0.5, {Faixa.NORMAL: 10.0, **REV}) == Faixa.NORMAL


# ---------- _valor_em ----------


def serie(*pares: tuple[int, float]) -> list[tuple[datetime, float]]:
    """(minutos antes de T0, valor)."""
    return [(T0 - timedelta(minutes=m), v) for m, v in pares]


def test_valor_em_aceita_ate_7_minutos_de_distancia_inclusive() -> None:
    alvo = T0 - timedelta(hours=1)
    assert _valor_em(serie((67, 1.0)), alvo) == 1.0  # 7 min depois do alvo (mais antigo)
    assert _valor_em(serie((53, 1.0)), alvo) == 1.0  # 7 min antes do alvo (mais novo)


def test_valor_em_recusa_alem_de_7_minutos() -> None:
    alvo = T0 - timedelta(hours=1)
    pontos = [(alvo + TOLERANCIA_PONTO + timedelta(seconds=1), 1.0)]
    assert _valor_em(pontos, alvo) is None
    assert _valor_em([(alvo - TOLERANCIA_PONTO - timedelta(seconds=1), 1.0)], alvo) is None


def test_valor_em_escolhe_o_mais_proximo_mesmo_com_serie_desordenada() -> None:
    alvo = T0 - timedelta(hours=1)
    pontos = serie((64, 9.0), (59, 5.0), (62, 7.0), (56, 3.0))
    assert _valor_em(pontos, alvo) == 5.0  # 1 min de distancia
    assert _valor_em([], alvo) is None


def test_valor_em_empate_de_distancia_fica_com_o_primeiro_da_lista() -> None:
    alvo = T0 - timedelta(hours=1)
    pontos = serie((62, 1.0), (58, 2.0))  # 2 min para cada lado
    assert _valor_em(pontos, alvo) == 1.0


# ---------- taxa e aceleracao ----------


def test_taxa_negativa_quando_o_nivel_desce() -> None:
    taxa, acel = taxa_e_aceleracao(serie((0, 2.0), (60, 2.15), (120, 2.20)))
    assert taxa == pytest.approx(-15.0) and acel == pytest.approx(-10.0)


def test_aceleracao_negativa_quando_a_subida_desacelera() -> None:
    taxa, acel = taxa_e_aceleracao(serie((0, 2.10), (60, 2.00), (120, 1.80)))
    assert taxa == pytest.approx(10.0) and acel == pytest.approx(-10.0)


def test_sem_leitura_de_duas_horas_atras_so_ha_taxa() -> None:
    taxa, acel = taxa_e_aceleracao(serie((0, 2.10), (60, 2.00)))
    assert taxa == pytest.approx(10.0) and acel is None


def test_leitura_de_uma_hora_atras_a_mais_de_7_min_nao_conta() -> None:
    assert taxa_e_aceleracao(serie((0, 2.1), (68, 2.0))) == (None, None)


def test_ultimo_ponto_e_o_mais_recente_mesmo_com_serie_desordenada() -> None:
    desordenada = serie((60, 2.0), (0, 2.1), (120, 1.9))
    assert taxa_e_aceleracao(desordenada)[0] == pytest.approx(10.0)


def test_taxa_arredondada_em_uma_casa() -> None:
    taxa, _ = taxa_e_aceleracao(serie((0, 2.0123), (60, 2.0)))
    assert taxa == 1.2


def test_nivel_constante_tem_taxa_e_aceleracao_zero() -> None:
    taxa, acel = taxa_e_aceleracao(serie((0, 1.0), (60, 1.0), (120, 1.0)))
    assert (taxa, acel) == (0.0, 0.0)


# ---------- tendencia ----------


@pytest.mark.parametrize(
    ("taxa", "esperada"),
    [
        (2.0001, "subindo"),
        (2.0, "estavel"),
        (-2.0, "estavel"),
        (-2.0001, "descendo"),
        (0.0, "estavel"),
        (100.0, "subindo"),
        (-100.0, "descendo"),
    ],
)
def test_tendencia_nas_fronteiras_do_limite_de_2_cm_por_hora(taxa: float, esperada: str) -> None:
    assert tendencia(taxa) == esperada
