"""Regra de alerta por nivel observado (CDU07, RN02, RN03, RN04) e a histerese (RN10).

Funcoes puras de decisao + aplicacao no banco. O estado "faixa vigente" de uma estacao e o
alerta aberto mais recente (encerrado_em nulo); sem alerta aberto, a faixa vigente e normal.

Regras:
- RN02: so ha alerta (e push) na transicao para faixa MAIS grave.
- RN04: dado desatualizado nunca dispara alerta nem encerra um alerta aberto.
- RN10 (histerese): para voltar a uma faixa menos grave, as ULTIMAS 3 leituras validas precisam
  estar todas abaixo da faixa vigente. A faixa de destino e a mais alta entre elas. Sem isso, um
  nivel oscilando em torno do limiar geraria entra-e-sai de alerta.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from common.enums import Faixa, Variavel
from common.models import Alerta, Estacao
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import consultas, risco

LEITURAS_PARA_DESCER = 3
ORDEM = {f: i for i, f in enumerate(risco.ORDEM)}


@dataclass(frozen=True)
class Transicao:
    tipo: Literal["escala", "desce"]
    de: Faixa
    para: Faixa


def decidir(
    vigente: Faixa,
    leituras: list[tuple[datetime, float]],
    limiares: dict[Faixa, float],
    agora: datetime,
    desatualizado_apos: timedelta,
) -> Transicao | None:
    """Decide se ha transicao. `leituras` vem ordenada da mais recente para a mais antiga."""
    if not leituras or not limiares:
        return None
    mais_recente = leituras[0][0]
    if agora - mais_recente > desatualizado_apos:
        return None  # RN04
    atual = risco.classificar(leituras[0][1], limiares)
    if ORDEM[atual] > ORDEM[vigente]:
        return Transicao("escala", vigente, atual)
    if ORDEM[atual] < ORDEM[vigente]:
        ultimas = leituras[:LEITURAS_PARA_DESCER]
        if len(ultimas) < LEITURAS_PARA_DESCER:
            return None
        faixas = [risco.classificar(v, limiares) for _, v in ultimas]
        destino = max(faixas, key=lambda f: ORDEM[f])
        if ORDEM[destino] < ORDEM[vigente]:
            return Transicao("desce", vigente, destino)
    return None


def alerta_aberto(s: Session, estacao_id: int) -> Alerta | None:
    return s.scalar(
        select(Alerta)
        .where(Alerta.estacao_id == estacao_id, Alerta.encerrado_em.is_(None))
        .order_by(Alerta.criado_em.desc(), Alerta.id.desc())
        .limit(1)
    )


def faixa_vigente(s: Session, estacao_id: int) -> Faixa:
    aberto = alerta_aberto(s, estacao_id)
    return Faixa(aberto.faixa_nova) if aberto else Faixa.NORMAL


def aplicar(s: Session, estacao_id: int, t: Transicao, agora: datetime) -> Alerta | None:
    """Grava a transicao. Devolve o alerta NOVO quando houver (o que dispara notificacao).

    Subida: fecha o alerta aberto e abre outro na faixa nova.
    Descida para faixa ainda nao normal: fecha o aberto e abre outro (sem notificar a subida).
    Volta ao normal: so fecha o episodio.
    """
    aberto = alerta_aberto(s, estacao_id)
    if aberto is not None:
        aberto.encerrado_em = agora
    if t.para == Faixa.NORMAL:
        s.flush()
        return None
    novo = Alerta(
        estacao_id=estacao_id,
        faixa_anterior=t.de.value,
        faixa_nova=t.para.value,
        severidade=t.para.value,
        origem="observado",
        criado_em=agora,
    )
    s.add(novo)
    s.flush()
    return novo


def avaliar_estacao(
    s: Session, est: Estacao, agora: datetime, desatualizado_apos: timedelta
) -> tuple[Transicao, Alerta | None] | None:
    limiares = consultas.limiares_vigentes(s, est.id)
    serie = consultas.ultimas_leituras(s, est.id, Variavel.NIVEL_M, LEITURAS_PARA_DESCER)
    t = decidir(faixa_vigente(s, est.id), serie, limiares, agora, desatualizado_apos)
    if t is None:
        return None
    return t, aplicar(s, est.id, t, agora)


def avaliar_todas(
    s: Session, agora: datetime, desatualizado_apos: timedelta
) -> list[tuple[Estacao, Transicao, Alerta | None]]:
    saida = []
    for est in s.scalars(select(Estacao).where(Estacao.ativa, Estacao.papel == "alvo")):
        r = avaliar_estacao(s, est, agora, desatualizado_apos)
        if r is not None:
            saida.append((est, r[0], r[1]))
    return saida
