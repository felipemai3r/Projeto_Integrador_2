"""Carga inicial: baixa a janela historica da API REST, dia a dia, por estacao.

Uso: python -m ingestor.carga_inicial --dias 80
Roda uma vez no primeiro dia de operacao. A janela da fonte e deslizante: o que sai dela nao volta.
Pode ser reexecutada com seguranca (nao duplica).
"""

import argparse
import logging
import time
from datetime import UTC, datetime, timedelta

from common.config import obter_configuracao
from common.db import sessao
from common.logs import configurar

from ingestor.adapters.dcsc_rest import DcscRest
from ingestor.erros import FonteIndisponivel
from ingestor.gravar import gravar
from ingestor.main import estacoes_ativas

log = logging.getLogger("ingestor.carga_inicial")


def carregar(dias: int, pausa_s: float = 0.2, apenas: list[str] | None = None) -> dict[str, int]:
    cfg = obter_configuracao()
    codigos = apenas or estacoes_ativas()
    rest = DcscRest(cfg.dcsc_rest_url, codigos)
    hoje = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    totais = dict.fromkeys(codigos, 0)
    for codigo in codigos:
        for d in range(dias, -1, -1):
            ini = hoje - timedelta(days=d)
            try:
                leituras = rest.coletar_estacao(codigo, ini, ini + timedelta(days=1))
            except FonteIndisponivel as e:
                log.warning("dia ignorado: %s", e)
                continue
            if leituras:
                with sessao() as s:
                    novas, _ = gravar(s, "dcsc_rest", leituras, datetime.now(UTC))
                totais[codigo] += novas
            time.sleep(pausa_s)
        log.info("estacao concluida: %s, %d leituras novas", codigo, totais[codigo])
    return totais


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=80)
    ap.add_argument("--estacao", action="append", help="limita a estacao (repetivel)")
    args = ap.parse_args()
    configurar(obter_configuracao().log_level)
    for cod, n in carregar(args.dias, apenas=args.estacao).items():
        print(f"{cod}: {n} leituras novas")
