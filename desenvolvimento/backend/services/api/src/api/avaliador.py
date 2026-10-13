"""Avaliador periodico de risco. Roda dentro da API, a cada minuto, com trava no banco.

A trava (pg_try_advisory_lock) garante UMA execucao por vez mesmo com varias instancias da API,
o que evita alerta e push duplicados.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from common.config import obter_configuracao
from common.db import obter_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.alertas import avaliar_todas

log = logging.getLogger("api.avaliador")
CHAVE_TRAVA = 7_300_001


def rodar_uma_vez(agora: datetime | None = None) -> int:
    """Uma rodada. Devolve quantas transicoes foram aplicadas (0 se nao obteve a trava)."""
    agora = agora or datetime.now(UTC)
    limite = timedelta(minutes=obter_configuracao().desatualizado_apos_min)
    with Session(obter_engine()) as s:
        if not s.scalar(text("select pg_try_advisory_lock(:k)"), {"k": CHAVE_TRAVA}):
            return 0
        try:
            feitas = avaliar_todas(s, agora, limite)
            s.commit()
            for est, t, alerta in feitas:
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
