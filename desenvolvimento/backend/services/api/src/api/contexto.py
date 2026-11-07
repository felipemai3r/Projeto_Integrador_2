"""Condicoes hidrologicas no momento informado de uma ocorrencia (RF24, CDU04 passo 6).

Associa a cada registro o nivel das estacoes alvo e a chuva acumulada em 24 h e em 72 h nos
pontos, vigentes na data e hora do ocorrido. A de 72 h e o indicador classico de encosta saturada,
usado para ler deslizamentos e movimentacao de terra. Se nao ha dado (anterior a coleta), grava
`disponivel: false` (E3).
"""

from datetime import datetime, timedelta
from typing import Any

from common.models import Estacao, Leitura
from sqlalchemy import func, select
from sqlalchemy.orm import Session

TOLERANCIA_NIVEL = timedelta(minutes=20)
MIN_LEITURAS_CHUVA_24H = 230  # de 288: cobertura minima de 80%
MIN_LEITURAS_CHUVA_72H = 691  # de 864: cobertura minima de 80%


def _chuva_acumulada(
    s: Session, estacao_id: int, quando: datetime, horas: int, minimo: int
) -> float | None:
    soma, n = s.execute(
        select(func.sum(Leitura.valor), func.count(Leitura.id)).where(
            Leitura.estacao_id == estacao_id,
            Leitura.variavel == "chuva_acumulada_mm",
            Leitura.qualidade == "ok",
            Leitura.medido_em > quando - timedelta(hours=horas),
            Leitura.medido_em <= quando,
        )
    ).one()
    return round(float(soma or 0.0), 1) if n >= minimo else None


def contexto_hidrologico(s: Session, quando: datetime) -> dict[str, Any]:
    niveis: dict[str, Any] = {}
    chuva: dict[str, float] = {}
    chuva_72h: dict[str, float] = {}
    for e in s.scalars(select(Estacao).where(Estacao.ativa).order_by(Estacao.codigo)):
        if e.papel == "alvo":
            linha = s.execute(
                select(Leitura.medido_em, Leitura.valor)
                .where(
                    Leitura.estacao_id == e.id,
                    Leitura.variavel == "nivel_m",
                    Leitura.qualidade == "ok",
                    Leitura.medido_em.between(quando - TOLERANCIA_NIVEL, quando + TOLERANCIA_NIVEL),
                )
                .order_by(func.abs(func.extract("epoch", Leitura.medido_em - quando)))
                .limit(1)
            ).first()
            if linha is not None:
                niveis[e.codigo] = {
                    "nivel_m": round(linha[1], 2),
                    "medido_em": linha[0].isoformat(),
                }
        if (mm := _chuva_acumulada(s, e.id, quando, 24, MIN_LEITURAS_CHUVA_24H)) is not None:
            chuva[e.codigo] = mm
        if (mm := _chuva_acumulada(s, e.id, quando, 72, MIN_LEITURAS_CHUVA_72H)) is not None:
            chuva_72h[e.codigo] = mm
    return {
        "disponivel": bool(niveis or chuva or chuva_72h),
        "niveis": niveis,
        "chuva_24h_mm": chuva,
        "chuva_72h_mm": chuva_72h,
    }
