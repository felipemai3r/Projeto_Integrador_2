"""Carga do historico longo de chuva horaria (ERA5, via Open-Meteo Archive).

Uso: python -m ingestor.carga_era5 --inicio 2020-11-01
Preenche o contexto de chuva anterior a janela de 80 dias da API REST (inclui o evento de
dezembro de 2020). ERA5 subestima picos convectivos: serve de contexto, não de verdade de campo.
O archive tem defasagem de cerca de 5 dias; o fim padrao respeita isso. Idempotente.
"""

import argparse
import logging
import time
from datetime import UTC, date, datetime, timedelta

from common.config import obter_configuracao
from common.db import sessao
from common.logs import configurar

from ingestor.adapters.openmeteo import OpenMeteo
from ingestor.gravar import gravar
from ingestor.main import pontos_ativos

log = logging.getLogger("ingestor.carga_era5")


def carregar(inicio: date, fim: date, pausa_s: float = 1.0) -> int:
    cfg = obter_configuracao()
    om = OpenMeteo(cfg.openmeteo_forecast_url, cfg.openmeteo_archive_url)
    total = 0
    for ponto in pontos_ativos():
        cursor = inicio
        while cursor <= fim:
            ate = min(date(cursor.year, 12, 31), fim)
            leituras = om.historico([ponto], cursor, ate)
            with sessao() as s:
                novas, _ = gravar(s, "openmeteo_archive", leituras, datetime.now(UTC))
            total += novas
            log.info("%s %s a %s: %d novas", ponto[0], cursor, ate, novas)
            cursor = ate + timedelta(days=1)
            time.sleep(pausa_s)
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(2020, 11, 1))
    ap.add_argument(
        "--fim", type=date.fromisoformat, default=datetime.now(UTC).date() - timedelta(days=6)
    )
    args = ap.parse_args()
    configurar(obter_configuracao().log_level)
    print(f"{carregar(args.inicio, args.fim)} leituras novas")
