"""Avaliador periodico de risco. Roda dentro da API, a cada minuto, com trava no banco.

A trava (pg_try_advisory_lock) garante UMA execucao por vez mesmo com varias instancias da API,
o que evita alerta e push duplicados.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from common.config import obter_configuracao
from common.db import obter_engine
from common.enums import Faixa, Variavel
from common.models import Alerta, Estacao
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from api import consultas, risco
from api.alertas import ORDEM, avaliar_todas
from api.push import Enviador, EnviadorWebPush, notificar_abertura, notificar_encerramento

log = logging.getLogger("api.avaliador")
CHAVE_TRAVA = 7_300_001


def rodar_uma_vez(agora: datetime | None = None, enviador: Enviador | None = None) -> int:
    """Uma rodada. Devolve quantas transicoes foram aplicadas (0 se nao obteve a trava)."""
    agora = agora or datetime.now(UTC)
    enviador = enviador or EnviadorWebPush()
    limite = timedelta(minutes=obter_configuracao().desatualizado_apos_min)
    with Session(obter_engine()) as s:
        if not s.scalar(text("select pg_try_advisory_lock(:k)"), {"k": CHAVE_TRAVA}):
            return 0
        try:
            feitas = avaliar_todas(s, agora, limite)
            s.commit()
            for est, t, alerta in feitas:
                _notificar(s, est, t.para.value, alerta, enviador)
                s.commit()
                log.info(
                    "transicao de faixa",
                    extra={
                        "extra_campos": {
                            "estacao": est.codigo,
                            "tipo": t.tipo,
                            "de": t.de.value,
                            "para": t.para.value,
                            "alerta_id": alerta.id if alerta else None,
                        }
                    },
                )
            return len(feitas)
        finally:
            s.execute(text("select pg_advisory_unlock(:k)"), {"k": CHAVE_TRAVA})
            s.commit()


def _notificar(
    s: Session, est: Estacao, para: str, novo: Alerta | None, enviador: Enviador
) -> None:
    """Push depois do commit da transicao. Falha de envio nunca desfaz o alerta."""
    try:
        ultimo = consultas.ultima_leitura(s, est.id, Variavel.NIVEL_M)
        nivel = ultimo[0].valor if ultimo else None
        if novo is not None:
            # RN02: so a subida notifica. Descida para faixa ainda nao normal nao gera push.
            if ORDEM[Faixa(novo.faixa_nova)] > ORDEM[Faixa(novo.faixa_anterior)]:
                serie = (
                    consultas.serie_recente(s, est.id, Variavel.NIVEL_M, ultimo[0].medido_em, 150)
                    if ultimo
                    else []
                )
                taxa, _ = risco.taxa_e_aceleracao(serie)
                notificar_abertura(s, est, novo, enviador, nivel, risco.tendencia(taxa))
        elif para == "normal":
            encerrado = s.scalar(
                select(Alerta)
                .where(Alerta.estacao_id == est.id, Alerta.encerrado_em.is_not(None))
                .order_by(Alerta.encerrado_em.desc(), Alerta.id.desc())
                .limit(1)
            )
            if encerrado is not None:
                notificar_encerramento(s, est, encerrado, enviador, nivel)
    except Exception:
        log.exception("falha ao notificar", extra={"extra_campos": {"estacao": est.codigo}})


def iniciar() -> BackgroundScheduler:
    def tarefa() -> None:
        try:
            rodar_uma_vez()
        except Exception:
            log.exception("falha na rodada do avaliador")

    sch = BackgroundScheduler(timezone="UTC")
    sch.add_job(
        tarefa,
        "interval",
        seconds=60,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC) + timedelta(seconds=5),
    )
    sch.start()
    return sch
