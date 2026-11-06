from datetime import datetime, timedelta
from typing import Annotated

from common.config import obter_configuracao
from common.enums import Faixa, Variavel
from common.models import Estacao, Fonte, Leitura
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from api import consultas, risco
from api.deps import obter_agora, obter_sessao
from api.schemas import EstacaoOut, NivelAtual, PontoSerie, Serie

router = APIRouter(prefix="/estacoes", tags=["estacoes"])

SessaoDep = Annotated[Session, Depends(obter_sessao)]
AgoraDep = Annotated[datetime, Depends(obter_agora)]


@router.get("", response_model=list[EstacaoOut])
def listar(s: SessaoDep) -> list[EstacaoOut]:
    estacoes = s.scalars(select(Estacao).where(Estacao.ativa).order_by(Estacao.codigo))
    return [consultas.estacao_out(s, e) for e in estacoes]


@router.get("/{codigo}/atual", response_model=NivelAtual)
def atual(codigo: str, s: SessaoDep, agora: AgoraDep) -> NivelAtual:
    est = consultas.obter_estacao(s, codigo)
    if est is None:
        raise HTTPException(404, f"Estação {codigo} não encontrada")
    saida = consultas.estacao_out(s, est)

    achado = consultas.ultima_leitura(s, est.id, Variavel.NIVEL_M)
    if achado is None:
        return NivelAtual(
            estacao=saida,
            estado="indisponivel",
            motivo="Esta estação não tem leitura de nível do rio.",
        )
    leitura, fonte = achado
    assert leitura.valor is not None
    estado = consultas.estado_do_dado(
        leitura.medido_em, agora, obter_configuracao().desatualizado_apos_min
    )
    limiares = consultas.limiares_vigentes(s, est.id)
    faixa = risco.classificar(leitura.valor, limiares) if limiares else None
    serie = consultas.serie_recente(s, est.id, Variavel.NIVEL_M, leitura.medido_em, 150)
    taxa, aceleracao = risco.taxa_e_aceleracao(serie)
    return NivelAtual(
        estacao=saida,
        estado=estado,
        nivel_m=leitura.valor,
        faixa=faixa.value if isinstance(faixa, Faixa) else None,
        taxa_cm_h=taxa,
        aceleracao_cm_h2=aceleracao,
        tendencia=risco.tendencia(taxa),
        medido_em=leitura.medido_em,
        fonte=fonte,
        motivo="Dado desatualizado: a fonte não publicou leitura recente."
        if estado == "desatualizado"
        else None,
    )


def _passo_padrao(horas: int) -> int:
    if horas <= 24:
        return 5
    if horas <= 72:
        return 15
    return 30 if horas <= 168 else 60


@router.get("/{codigo}/serie", response_model=Serie)
def serie(
    codigo: str,
    s: SessaoDep,
    agora: AgoraDep,
    variavel: Variavel = Variavel.NIVEL_M,
    horas: Annotated[int, Query(ge=1, le=720)] = 24,
    passo_min: Annotated[int | None, Query(ge=5, le=240)] = None,
) -> Serie:
    est = consultas.obter_estacao(s, codigo)
    if est is None:
        raise HTTPException(404, f"Estação {codigo} não encontrada")
    passo = passo_min or _passo_padrao(horas)
    # passo e inteiro validado acima: seguro para interpolar no literal de intervalo
    balde = func.date_bin(
        literal_column(f"interval '{int(passo)} minutes'"),
        Leitura.medido_em,
        literal_column("timestamptz '2000-01-01 00:00:00+00'"),
    ).label("t")
    linhas = s.execute(
        select(balde, func.avg(Leitura.valor), func.max(Leitura.unidade))
        .join(Fonte, Fonte.id == Leitura.fonte_id)
        .where(
            Leitura.estacao_id == est.id,
            Leitura.variavel == variavel.value,
            Leitura.qualidade == "ok",
            Leitura.valor.is_not(None),
            Fonte.codigo != "openmeteo_archive",  # reanalise ERA5 nao e medicao
            Leitura.medido_em >= agora - timedelta(hours=horas),
            Leitura.medido_em <= agora,
        )
        .group_by(balde)
        .order_by(balde)
    ).all()
    return Serie(
        estacao=est.codigo,
        variavel=variavel.value,
        unidade=linhas[-1][2] if linhas else "",
        passo_min=passo,
        pontos=[PontoSerie(medido_em=t, valor=round(v, 3)) for t, v, _ in linhas],
    )
