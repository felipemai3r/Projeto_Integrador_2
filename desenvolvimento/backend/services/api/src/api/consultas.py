"""Consultas reutilizadas pelos routers."""

from datetime import datetime, timedelta

from common.enums import Faixa, Qualidade, Variavel
from common.models import Estacao, Fonte, Leitura, Limiar
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import EstacaoOut, EstadoDado, Limiares


def obter_estacao(s: Session, codigo: str) -> Estacao | None:
    return s.scalar(select(Estacao).where(Estacao.codigo == codigo, Estacao.ativa))


def limiares_vigentes(s: Session, estacao_id: int) -> dict[Faixa, float]:
    """Limiar mais recente de cada faixa (a tabela guarda o historico, RN08)."""
    linhas = s.scalars(
        select(Limiar).where(Limiar.estacao_id == estacao_id).order_by(Limiar.vigente_desde.desc())
    )
    vigentes: dict[Faixa, float] = {}
    for li in linhas:
        faixa = Faixa(li.faixa)
        vigentes.setdefault(faixa, li.valor_m)
    return vigentes


def estacao_out(s: Session, e: Estacao) -> EstacaoOut:
    lim = limiares_vigentes(s, e.id)
    return EstacaoOut(
        codigo=e.codigo,
        nome=e.nome,
        curso_dagua=e.curso_dagua,
        papel=e.papel,
        latitude=e.latitude,
        longitude=e.longitude,
        limiares=Limiares(
            observacao=lim.get(Faixa.OBSERVACAO),
            atencao=lim.get(Faixa.ATENCAO),
            alerta=lim.get(Faixa.ALERTA),
        ),
    )


def ultima_leitura(s: Session, estacao_id: int, variavel: Variavel) -> tuple[Leitura, str] | None:
    """Ultima leitura valida (qualidade ok) e o codigo da fonte."""
    linha = s.execute(
        select(Leitura, Fonte.codigo)
        .join(Fonte, Fonte.id == Leitura.fonte_id)
        .where(
            Leitura.estacao_id == estacao_id,
            Leitura.variavel == variavel.value,
            Leitura.qualidade == Qualidade.OK.value,
            Leitura.valor.is_not(None),
        )
        .order_by(Leitura.medido_em.desc())
        .limit(1)
    ).first()
    return (linha[0], linha[1]) if linha else None


def serie_recente(
    s: Session, estacao_id: int, variavel: Variavel, ate: datetime, minutos: int
) -> list[tuple[datetime, float]]:
    linhas = s.execute(
        select(Leitura.medido_em, Leitura.valor).where(
            Leitura.estacao_id == estacao_id,
            Leitura.variavel == variavel.value,
            Leitura.qualidade == Qualidade.OK.value,
            Leitura.valor.is_not(None),
            Leitura.medido_em <= ate,
            Leitura.medido_em >= ate - timedelta(minutes=minutos),
        )
    ).all()
    return [(t, v) for t, v in linhas]


def estado_do_dado(medido_em: datetime | None, agora: datetime, limite_min: int) -> EstadoDado:
    if medido_em is None:
        return "indisponivel"
    return "desatualizado" if agora - medido_em > timedelta(minutes=limite_min) else "ok"


def ultimas_leituras(
    s: Session, estacao_id: int, variavel: Variavel, n: int
) -> list[tuple[datetime, float]]:
    """As `n` leituras validas mais recentes, da mais nova para a mais antiga."""
    linhas = s.execute(
        select(Leitura.medido_em, Leitura.valor)
        .where(
            Leitura.estacao_id == estacao_id,
            Leitura.variavel == variavel.value,
            Leitura.qualidade == Qualidade.OK.value,
            Leitura.valor.is_not(None),
        )
        .order_by(Leitura.medido_em.desc())
        .limit(n)
    ).all()
    return [(t, v) for t, v in linhas]
