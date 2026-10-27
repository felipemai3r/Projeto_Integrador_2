"""Classificacao de risco e tendencia do nivel. Funcoes puras, sem banco (RF09, RF10, RN01).

Faixa: a mais grave cujo limiar o nivel atingiu (>=). Abaixo de todos os limiares e `normal`.
Faixa sem limiar cadastrado (hoje, `extremo`) nunca e atingida.
"""

from datetime import datetime, timedelta

from common.enums import Faixa

ORDEM = [Faixa.NORMAL, Faixa.ATENCAO, Faixa.ALERTA, Faixa.ALERTA_ALTO, Faixa.EXTREMO]
TOLERANCIA_PONTO = timedelta(minutes=7)
LIMITE_ESTAVEL_CM_H = 2.0  # variacao menor que isso em 1 h e considerada estavel


def classificar(nivel_m: float, limiares: dict[Faixa, float]) -> Faixa:
    faixa = Faixa.NORMAL
    for f in ORDEM[1:]:
        limiar = limiares.get(f)
        if limiar is not None and nivel_m >= limiar:
            faixa = f
    return faixa


def _valor_em(serie: list[tuple[datetime, float]], alvo: datetime) -> float | None:
    """Leitura mais proxima de `alvo`, dentro da tolerancia. `serie` nao precisa estar ordenada."""
    melhor: tuple[timedelta, float] | None = None
    for t, v in serie:
        d = abs(t - alvo)
        if d <= TOLERANCIA_PONTO and (melhor is None or d < melhor[0]):
            melhor = (d, v)
    return melhor[1] if melhor else None


def taxa_e_aceleracao(
    serie: list[tuple[datetime, float]],
) -> tuple[float | None, float | None]:
    """Taxa (cm/h) e aceleracao (cm/h2) a partir do ultimo ponto.

    taxa = (nivel agora - nivel ha 1 h) em cm; aceleracao = taxa agora - taxa de 1 h atras.
    Devolve None onde nao ha leitura proxima o bastante dos instantes necessarios.
    """
    if not serie:
        return None, None
    t0, v0 = max(serie, key=lambda p: p[0])
    v1 = _valor_em(serie, t0 - timedelta(hours=1))
    v2 = _valor_em(serie, t0 - timedelta(hours=2))
    taxa = round((v0 - v1) * 100, 1) if v1 is not None else None
    taxa_anterior = round((v1 - v2) * 100, 1) if v1 is not None and v2 is not None else None
    aceleracao = (
        round(taxa - taxa_anterior, 1) if taxa is not None and taxa_anterior is not None else None
    )
    return taxa, aceleracao


def tendencia(taxa_cm_h: float | None) -> str | None:
    if taxa_cm_h is None:
        return None
    if taxa_cm_h > LIMITE_ESTAVEL_CM_H:
        return "subindo"
    if taxa_cm_h < -LIMITE_ESTAVEL_CM_H:
        return "descendo"
    return "estavel"
