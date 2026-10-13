"""Condicoes hidrologicas no momento informado de uma ocorrencia (RF24, CDU04 passo 6).

Associa a cada registro o nivel das estacoes alvo e a chuva acumulada em 24 h nos pontos, vigentes
na data e hora do ocorrido. Se nao ha dado (anterior a coleta), grava `disponivel: false` (E3).
"""

from datetime import datetime, timedelta
from typing import Any

from common.models import Estacao, Leitura
from sqlalchemy import func, select
from sqlalchemy.orm import Session

TOLERANCIA_NIVEL = timedelta(minutes=20)
MIN_LEITURAS_CHUVA_24H = 230  # de 288: cobertura minima de 80%


def contexto_hidrologico(s: Session, quando: datetime) -> dict[str, Any]:
    niveis: dict[str, Any] = {}
    chuva: dict[str, float | None] = {}
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
        soma = s.execute(
            select(func.sum(Leitura.valor), func.count(Leitura.id)).where(
                Leitura.estacao_id == e.id,
                Leitura.variavel == "chuva_acumulada_mm",
                Leitura.qualidade == "ok",
                Leitura.medido_em > quando - timedelta(hours=24),
                Leitura.medido_em <= quando,
            )
        ).one()
        if soma[1] >= MIN_LEITURAS_CHUVA_24H:
            chuva[e.codigo] = round(float(soma[0] or 0.0), 1)
    return {"disponivel": bool(niveis or chuva), "niveis": niveis, "chuva_24h_mm": chuva}
