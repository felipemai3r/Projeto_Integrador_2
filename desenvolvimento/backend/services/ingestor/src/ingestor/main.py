"""Agendador do ingestor. Roda como processo unico (docs/arquitetura-desenvolvimento.md, 5.4)."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from common.config import obter_configuracao
from common.db import sessao
from common.logs import configurar
from common.models import Estacao
from sqlalchemy import select

from ingestor.adapters.dcsc_barragens import DcscBarragens
from ingestor.adapters.dcsc_graphql import DcscGraphql
from ingestor.adapters.dcsc_rest import DcscRest
from ingestor.adapters.openmeteo import OpenMeteo, Ponto
from ingestor.coleta import executar
from ingestor.gravar import gravar_previsoes

log = logging.getLogger("ingestor")


def estacoes_ativas() -> list[str]:
    with sessao() as s:
        return list(s.scalars(select(Estacao.codigo).where(Estacao.ativa)))


def verificar_silencio(limite_min: int = 15) -> None:
    """O primeiro sintoma de problema grave e o silencio: sem leitura nova, grita no log."""
    from common.models import Leitura
    from sqlalchemy import func

    with sessao() as s:
        ultima = s.scalar(select(func.max(Leitura.coletado_em)))
    if ultima is None or datetime.now(UTC) - ultima > timedelta(minutes=limite_min):
        log.error(
            "COLETA EM SILENCIO: nenhuma leitura nova",
            extra={"extra_campos": {"ultima_coleta": str(ultima), "limite_min": limite_min}},
        )


def pontos_ativos() -> list[Ponto]:
    with sessao() as s:
        return [
            (e.codigo, e.latitude, e.longitude)
            for e in s.scalars(select(Estacao).where(Estacao.ativa))
        ]


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

    barragens = DcscBarragens(cfg.dcsc_rest_url)
    openmeteo = OpenMeteo(cfg.openmeteo_forecast_url, cfg.openmeteo_archive_url)

    def coletar_barragens() -> None:
        executar("dcsc_barragens", barragens.coletar)

    def coletar_previsao() -> None:
        executar(
            "openmeteo_forecast", lambda: openmeteo.previsao(pontos_ativos()), gravar_previsoes
        )

    def canario_de_contrato() -> None:
        """Compara a resposta real de cada fonte com a esperada e avisa quando mudar."""
        pontos = pontos_ativos()
        resultado = {
            "dcsc_graphql": graphql.verificar_contrato(),
            "dcsc_barragens": barragens.verificar_contrato(),
            "dcsc_rest": DcscRest(cfg.dcsc_rest_url, [p[0] for p in pontos]).verificar_contrato(),
            "openmeteo_forecast": openmeteo.verificar_contrato(pontos[0]),
        }
        for fonte, ok in resultado.items():
            nivel = logging.INFO if ok else logging.ERROR
            log.log(
                nivel, "canario de contrato", extra={"extra_campos": {"fonte": fonte, "ok": ok}}
            )

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
    sch.add_job(
        coletar_barragens,
        "interval",
        minutes=30,
        next_run_time=datetime.now(UTC) + timedelta(seconds=60),
        **kw,
    )
    sch.add_job(
        coletar_previsao,
        "interval",
        hours=1,
        next_run_time=datetime.now(UTC) + timedelta(seconds=90),
        **kw,
    )
    sch.add_job(canario_de_contrato, "cron", hour=9, minute=0, **kw)
    sch.add_job(verificar_silencio, "interval", minutes=5, **kw)
    log.info("ingestor iniciado")
    sch.start()


if __name__ == "__main__":
    main()
