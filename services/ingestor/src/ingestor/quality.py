"""Validacao de plausibilidade fisica (RF07). Funcoes puras, sem banco.

Regras (docs/arquitetura-desenvolvimento.md, secao 5.5):
- nivel negativo ou acima de 15 m: descartada
- salto de nivel maior que 100 cm entre leituras de 5 minutos: suspeita
- chuva acumulada de 1h acima de 150 mm: suspeita
- carimbo de tempo no futuro: descartada
"""

from datetime import datetime, timedelta

from common.enums import Qualidade, Variavel
from common.schemas import LeituraBruta

NIVEL_MAX_M = 15.0
SALTO_MAX_M = 1.0
JANELA_SALTO = timedelta(minutes=5)
CHUVA_H001_MAX_MM = 150.0
TOLERANCIA_RELOGIO = timedelta(minutes=2)


def avaliar(
    leitura: LeituraBruta,
    agora: datetime,
    anterior: tuple[datetime, float] | None = None,
) -> Qualidade:
    """Classifica a leitura. `anterior` e (medido_em, valor) da leitura anterior da serie."""
    if leitura.medido_em > agora + TOLERANCIA_RELOGIO:
        return Qualidade.DESCARTADA
    v = leitura.valor
    if v is None:
        return Qualidade.DESCARTADA

    if leitura.variavel == Variavel.NIVEL_M:
        if v < 0 or v > NIVEL_MAX_M:
            return Qualidade.DESCARTADA
        if anterior is not None:
            dt = leitura.medido_em - anterior[0]
            if timedelta(0) < dt <= JANELA_SALTO and abs(v - anterior[1]) > SALTO_MAX_M:
                return Qualidade.SUSPEITA
    elif leitura.variavel.value.startswith("chuva_"):
        if v < 0:
            return Qualidade.DESCARTADA
        if leitura.variavel == Variavel.CHUVA_H001_MM and v > CHUVA_H001_MAX_MM:
            return Qualidade.SUSPEITA
    return Qualidade.OK
