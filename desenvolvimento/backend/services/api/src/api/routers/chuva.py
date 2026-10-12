from datetime import datetime
from typing import Annotated

from common.config import obter_configuracao
from common.models import Estacao, Fonte, Leitura
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from api import consultas
from api.deps import obter_agora, obter_sessao
from api.schemas import ChuvaEstacao

router = APIRouter(prefix="/chuva", tags=["chuva"])

JANELAS = {
    "chuva_h001_mm": "1h",
    "chuva_h003_mm": "3h",
    "chuva_h006_mm": "6h",
    "chuva_h012_mm": "12h",
    "chuva_h024_mm": "24h",
    "chuva_h048_mm": "48h",
    "chuva_h072_mm": "72h",
    "chuva_h168_mm": "168h",
}


@router.get("/acumulada", response_model=list[ChuvaEstacao])
def acumulada(
    s: Annotated[Session, Depends(obter_sessao)],
    agora: Annotated[datetime, Depends(obter_agora)],
) -> list[ChuvaEstacao]:
    """Chuva acumulada por janela em cada estacao, a ultima leitura do GraphQL (RF17)."""
    limite = obter_configuracao().desatualizado_apos_min
    ultimas = s.execute(
        select(Leitura.estacao_id, Leitura.variavel, Leitura.valor, Leitura.medido_em)
        .ext(distinct_on(Leitura.estacao_id, Leitura.variavel))
        .join(Fonte, Fonte.id == Leitura.fonte_id)
        .where(
            Fonte.codigo == "dcsc_graphql",
            Leitura.variavel.in_(list(JANELAS)),
            Leitura.qualidade == "ok",
        )
        .order_by(Leitura.estacao_id, Leitura.variavel, Leitura.medido_em.desc())
    ).all()
    por_estacao: dict[int, dict[str, tuple[float | None, datetime]]] = {}
    for est_id, var, valor, medido in ultimas:
        por_estacao.setdefault(est_id, {})[JANELAS[var]] = (valor, medido)

    saida: list[ChuvaEstacao] = []
    for e in s.scalars(select(Estacao).where(Estacao.ativa).order_by(Estacao.codigo)):
        janelas = por_estacao.get(e.id, {})
        medido_em = max((m for _, m in janelas.values()), default=None)
        saida.append(
            ChuvaEstacao(
                estacao=e.codigo,
                nome=e.nome,
                papel=e.papel,
                estado=consultas.estado_do_dado(medido_em, agora, limite),
                medido_em=medido_em,
                fonte="dcsc_graphql" if janelas else None,
                acumulado_mm={
                    j: (janelas[j][0] if j in janelas else None) for j in JANELAS.values()
                },
            )
        )
    return saida
