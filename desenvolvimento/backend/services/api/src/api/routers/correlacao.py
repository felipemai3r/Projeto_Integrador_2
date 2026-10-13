from typing import Annotated

from common.models import Correlacao, Estacao
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import obter_sessao
from api.schemas import CorrelacaoOut

router = APIRouter(prefix="/correlacao", tags=["analise"])


def _leitura(sinal: bool, p: float | None) -> str:
    if sinal:
        return "Há relação estatística entre os dois, com a defasagem indicada."
    if p is None:
        return "Dados insuficientes para afirmar."
    return "Sem relação clara nesta base: o acaso explica o resultado."


@router.get("", response_model=list[CorrelacaoOut])
def ultima_analise(
    s: Annotated[Session, Depends(obter_sessao)], estacao: str = "DCSC-00043"
) -> list[CorrelacaoOut]:
    """Resultados da rodada mais recente da correlacao defasada para a estacao alvo."""
    alvo = s.scalar(select(Estacao).where(Estacao.codigo == estacao))
    if alvo is None:
        raise HTTPException(404, f"Estação {estacao} não encontrada")
    ultima = s.scalar(
        select(func.max(Correlacao.calculado_em)).where(Correlacao.estacao_alvo_id == alvo.id)
    )
    if ultima is None:
        return []
    linhas = s.execute(
        select(Correlacao, Estacao)
        .join(Estacao, Estacao.id == Correlacao.ponto_id)
        .where(Correlacao.estacao_alvo_id == alvo.id, Correlacao.calculado_em == ultima)
        .order_by(Correlacao.explicativa, Correlacao.r.desc())
    ).all()
    saida = []
    for c, ponto in linhas:
        sinal = c.p_valor is not None and c.p_valor < 0.05 and c.r > 0
        saida.append(
            CorrelacaoOut(
                ponto=ponto.codigo,
                nome=ponto.nome,
                explicativa=c.explicativa,
                melhor_defasagem_h=c.melhor_defasagem_h,
                r=c.r,
                ic_inf=c.ic_inf,
                ic_sup=c.ic_sup,
                p_valor=c.p_valor,
                horas_validas=c.horas_validas,
                sinal_claro=sinal,
                leitura=_leitura(sinal, c.p_valor),
                janela_chuva_h=c.janela_chuva_h,
                periodo_inicio=c.periodo_inicio,
                periodo_fim=c.periodo_fim,
                calculado_em=c.calculado_em,
            )
        )
    return saida
