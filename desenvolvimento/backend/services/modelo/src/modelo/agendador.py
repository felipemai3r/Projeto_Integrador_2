"""Retreino periodico dos modelos (CDU12). Roda como servico proprio.

Todo dia as 07:00 UTC treina cada alvo (`modelo.features.ALVOS`: rio dos Indios e Ribeirao
Revolver), valida contra os baselines e registra. O modelo so e PUBLICADO quando atende a RN07
(supera a persistencia e ha dado suficiente): a publicacao acontece sozinha no dia em que o
criterio for atendido, e e revogada sozinha se um treino futuro deixar de atende-lo.

Cada alvo e treinado isolado: a falha de um (sem leituras, erro de banco, dado ruim) e registrada
no log e nao impede o treino dos demais. Janela de treino: padrao por alvo (`ConfigAlvo`, ver
`modelo.treinar`); `--dias N` ou `--desde AAAA-MM-DD` na linha de comando do servico a
sobrescrevem para todos os alvos.
"""

import argparse
import logging
from datetime import date

from apscheduler.schedulers.blocking import BlockingScheduler
from common.config import obter_configuracao
from common.logs import configurar

from modelo.features import ALVOS
from modelo.treinar import treinar

log = logging.getLogger("modelo.agendador")


def rodar(
    alvos: tuple[str, ...] | None = None, dias: int | None = None, desde: date | None = None
) -> dict[str, bool]:
    """Treina cada alvo isoladamente. Devolve, por alvo, se o treino terminou sem erro."""
    ok: dict[str, bool] = {}
    for alvo in alvos or tuple(ALVOS):
        try:
            resultados = treinar(alvo, dias=dias, salvar=True, desde=desde)
        except Exception:
            # Exception (nao BaseException): um erro de um alvo nao pode parar os outros
            log.exception("falha no treino", extra={"extra_campos": {"alvo": alvo}})
            ok[alvo] = False
            continue
        ok[alvo] = True
        for r in resultados:
            log.info(
                "treino concluido",
                extra={
                    "extra_campos": {
                        "alvo": alvo,
                        "horizonte_h": r.horizonte_h,
                        "publicado": r.publicar,
                        "dias_uteis": r.dias_uteis,
                        "motivo": r.motivo,
                    }
                },
            )
    return ok


def principal() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dias", type=int, help="ultimos N dias (padrao: o de cada alvo)")
    ap.add_argument("--desde", type=date.fromisoformat, help="treina desde AAAA-MM-DD")
    args = ap.parse_args()
    configurar(obter_configuracao().log_level)
    sch = BlockingScheduler(timezone="UTC")
    sch.add_job(
        rodar,
        "cron",
        hour=7,
        minute=0,
        max_instances=1,
        coalesce=True,
        kwargs={"dias": args.dias, "desde": args.desde},
    )
    log.info("treinador agendado para 07:00 UTC", extra={"extra_campos": {"alvos": list(ALVOS)}})
    sch.start()


if __name__ == "__main__":
    principal()
