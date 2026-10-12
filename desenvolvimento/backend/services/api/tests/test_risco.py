from datetime import UTC, datetime, timedelta

import pytest
from common.enums import Faixa

from api.risco import classificar, taxa_e_aceleracao, tendencia

LIM = {Faixa.OBSERVACAO: 4.0, Faixa.ATENCAO: 4.5, Faixa.ALERTA: 5.5}
T0 = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("nivel", "esperada"),
    [
        (1.8, Faixa.NORMAL),
        (3.99, Faixa.NORMAL),
        (4.0, Faixa.OBSERVACAO),  # no limiar ja conta como atingido
        (4.49, Faixa.OBSERVACAO),
        (4.5, Faixa.ATENCAO),
        (5.49, Faixa.ATENCAO),
        (5.5, Faixa.ALERTA),
        (9.0, Faixa.ALERTA),
    ],
)
def test_classificacao_por_limiar(nivel: float, esperada: Faixa) -> None:
    assert classificar(nivel, LIM) == esperada


def test_faixa_ausente_nos_limiares_e_ignorada() -> None:
    assert classificar(5.0, {Faixa.ALERTA: 5.5}) == Faixa.NORMAL


def serie(valores_por_hora: list[float]) -> list[tuple[datetime, float]]:
    """Pontos de 5 em 5 minutos interpolando linearmente entre os valores horarios."""
    pts: list[tuple[datetime, float]] = []
    n = len(valores_por_hora) - 1
    for i in range(n * 12 + 1):
        h, r = divmod(i, 12)
        a = valores_por_hora[h]
        b = valores_por_hora[min(h + 1, n)]
        pts.append((T0 - timedelta(hours=n) + timedelta(minutes=5 * i), a + (b - a) * r / 12))
    return pts


def test_taxa_de_subida_em_cm_por_hora() -> None:
    taxa, _ = taxa_e_aceleracao(serie([1.00, 1.10, 1.22]))  # +12 cm na ultima hora
    assert taxa == pytest.approx(12.0, abs=0.2)


def test_aceleracao_positiva_quando_a_subida_aumenta() -> None:
    taxa, acel = taxa_e_aceleracao(serie([1.00, 1.10, 1.22]))  # 10 cm/h depois 12 cm/h
    assert acel == pytest.approx(2.0, abs=0.3)


def test_sem_historico_suficiente_devolve_none() -> None:
    assert taxa_e_aceleracao([]) == (None, None)
    so_agora = [(T0, 1.0)]
    assert taxa_e_aceleracao(so_agora) == (None, None)


def test_lacuna_longa_impede_calcular_taxa() -> None:
    pts = [(T0, 2.0), (T0 - timedelta(hours=3), 1.0)]
    assert taxa_e_aceleracao(pts) == (None, None)


@pytest.mark.parametrize(
    ("taxa", "esperada"),
    [(12.0, "subindo"), (2.0, "estavel"), (0.0, "estavel"), (-3.5, "descendo"), (None, None)],
)
def test_tendencia(taxa: float | None, esperada: str | None) -> None:
    assert tendencia(taxa) == esperada
