"""Agendador do ingestor. Roda como processo unico (docs/arquitetura-desenvolvimento.md, 5.4)."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from common.config import obter_configuracao
from common.db import sessao
from common.logs import configurar
from common.models import Estacao
from sqlalchemy import select

from ingestor.adapters.dcsc_graphql import DcscGraphql
from ingestor.adapters.dcsc_rest import DcscRest
from ingestor.coleta import executar

log = logging.getLogger("ingestor")


def estacoes_ativas() -> list[str]:
    with sessao() as s:
        return list(s.scalars(select(Estacao.codigo).where(Estacao.ativa)))


def main() -> None:
    cfg = obter_configuracao()
    configurar(cfg.log_level)
    graphql = DcscGraphql(cfg.dcsc_graphql_url)

    def coletar_graphql() -> None:
        executar("dcsc_graphql", graphql.coletar)

    def coletar_rest_lacunas() -> None:
        # janela de 6h cobre falhas curtas do GraphQL; reexecucao nao duplica
        rest = DcscRest(cfg.dcsc_rest_url, estacoes_ativas())
        fim = datetime.now(UTC)
        executar("dcsc_rest", lambda: rest.coletar(fim - timedelta(hours=6), fim))

    sch = BlockingScheduler(timezone="UTC")
    kw = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 120}
    sch.add_job(coletar_graphql, "interval", minutes=5, next_run_time=datetime.now(UTC), **kw)
    sch.add_job(
        coletar_rest_lacunas,
        "interval",
        minutes=30,
        next_run_time=datetime.now(UTC) + timedelta(seconds=30),
        **kw,
    )
    log.info("ingestor iniciado")
    sch.start()


if __name__ == "__main__":
    main()
