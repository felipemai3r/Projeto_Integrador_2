"""Retreino periodico dos modelos (CDU12). Roda como servico proprio.

Todo dia as 07:00 UTC treina, valida contra os baselines e registra. O modelo so e PUBLICADO
quando atende a RN07 (supera a persistencia e ha dado suficiente): a publicacao acontece sozinha
no dia em que o criterio for atendido, e e revogada sozinha se um treino futuro deixar de atende-lo.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from common.config import obter_configuracao
from common.logs import configurar

from modelo.features import ALVO
from modelo.treinar import treinar

log = logging.getLogger("modelo.agendador")


def rodar() -> None:
    try:
        resultados = treinar(ALVO, dias=120, salvar=True)
        for r in resultados:
            log.info(
                "treino concluido",
                extra={
                    "extra_campos": {
                        "horizonte_h": r.horizonte_h,
                        "publicado": r.publicar,
                        "dias_uteis": r.dias_uteis,
                        "motivo": r.motivo,
                    }
                },
            )
    except Exception:
        log.exception("falha no treino")


def principal() -> None:
    configurar(obter_configuracao().log_level)
    sch = BlockingScheduler(timezone="UTC")
    sch.add_job(rodar, "cron", hour=7, minute=0, max_instances=1, coalesce=True)
    log.info("treinador agendado para 07:00 UTC")
    sch.start()


if __name__ == "__main__":
    principal()
