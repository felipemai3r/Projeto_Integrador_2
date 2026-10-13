from typing import Annotated

from common.enums import Faixa, Variavel
from common.models import Alerta, Estacao
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import consultas
from api.alertas import ORDEM
from api.deps import obter_sessao
from api.schemas import AlertaOut

router = APIRouter(prefix="/alertas", tags=["alertas"])


@router.get("", response_model=list[AlertaOut])
def listar(
    s: Annotated[Session, Depends(obter_sessao)],
    vigentes: bool = False,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AlertaOut]:
    """Alertas vigentes (`vigentes=true`) ou o historico recente, do mais novo ao mais antigo."""
    q = select(Alerta, Estacao).join(Estacao, Estacao.id == Alerta.estacao_id)
    if vigentes:
        q = q.where(Alerta.encerrado_em.is_(None))
    linhas = s.execute(q.order_by(Alerta.criado_em.desc(), Alerta.id.desc()).limit(limite)).all()
    saida = []
    for a, e in linhas:
        ultimo = consultas.ultima_leitura(s, e.id, Variavel.NIVEL_M)
        saida.append(
            AlertaOut(
                id=a.id,
                estacao=e.codigo,
                nome=e.nome,
                curso_dagua=e.curso_dagua,
                faixa_anterior=a.faixa_anterior,
                faixa_nova=a.faixa_nova,
                sobe=ORDEM[Faixa(a.faixa_nova)] > ORDEM[Faixa(a.faixa_anterior)],
                origem=a.origem,
                criado_em=a.criado_em,
                encerrado_em=a.encerrado_em,
                vigente=a.encerrado_em is None,
                nivel_m=ultimo[0].valor if (vigentes and ultimo) else None,
            )
        )
    return saida
