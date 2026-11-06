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
    """Chuva acumulada por janela em cada estacao, a ultima leitura medida de cada janela (RF17).

    Fontes: GraphQL (todas as janelas) e painel municipal (so a de 1 h, e e a unica das estacoes
    DC-PEU-*). Vale a leitura mais recente por estacao e janela; janela sem dado volta nula.
    Nunca a reanalise ERA5, que nao e medicao.
    """
    limite = obter_configuracao().desatualizado_apos_min
    ultimas = s.execute(
        select(Leitura.estacao_id, Leitura.variavel, Leitura.valor, Leitura.medido_em, Fonte.codigo)
        .ext(distinct_on(Leitura.estacao_id, Leitura.variavel))
        .join(Fonte, Fonte.id == Leitura.fonte_id)
        .where(
            Fonte.codigo.in_(sorted(consultas.FONTES_MEDIDAS)),
            Leitura.variavel.in_(list(JANELAS)),
            Leitura.qualidade == "ok",
            Leitura.valor.is_not(None),
        )
        # empate de instante: a mesma ordem de preferencia das demais consultas
        .order_by(Leitura.estacao_id, Leitura.variavel, Leitura.medido_em.desc(), Fonte.codigo)
    ).all()
    por_estacao: dict[int, dict[str, tuple[float | None, datetime]]] = {}
    fonte_da_estacao: dict[int, tuple[datetime, str]] = {}
    for est_id, var, valor, medido, fonte in ultimas:
        por_estacao.setdefault(est_id, {})[JANELAS[var]] = (valor, medido)
        atual = fonte_da_estacao.get(est_id)
        if atual is None or medido > atual[0]:
            fonte_da_estacao[est_id] = (medido, fonte)

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
                fonte=fonte_da_estacao[e.id][1] if janelas else None,
                acumulado_mm={
                    j: (janelas[j][0] if j in janelas else None) for j in JANELAS.values()
                },
            )
        )
    return saida
