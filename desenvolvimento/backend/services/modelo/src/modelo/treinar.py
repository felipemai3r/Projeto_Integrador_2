"""Treina, valida e registra os modelos por horizonte (CDU12).

Uso: python -m modelo.treinar --estacao DCSC-00043
Roda sob demanda (e semanalmente no servidor). Mostra a validacao contra os baselines e diz,
para cada horizonte, se foi publicado ou por que nao.
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
from common.config import obter_configuracao
from common.db import sessao
from common.logs import configurar
from common.models import Estacao
from sqlalchemy import select

from modelo.dados import chuva_horaria, nivel_horario
from modelo.features import (
    ALVO,
    HORIZONTES_H,
    NIVEL_VIZINHOS,
    PONTOS_CHUVA,
    alvo_deslocado,
    montar_features,
)
from modelo.registry import registrar
from modelo.treino import Resultado, avaliar_horizonte

log = logging.getLogger("modelo.treinar")


def treinar(estacao: str, dias: int, salvar: bool) -> list[Resultado]:
    fim = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    inicio = fim - timedelta(days=dias)
    resultados: list[Resultado] = []
    with sessao() as s:
        est = s.scalar(select(Estacao).where(Estacao.codigo == estacao))
        if est is None:
            raise SystemExit(f"estacao {estacao} nao encontrada")
        chuva = {c: chuva_horaria(s, c, inicio, fim) for c in PONTOS_CHUVA}
        nivel = {c: nivel_horario(s, c, inicio, fim) for c in (estacao, *NIVEL_VIZINHOS)}
        chuva = {c: v for c, v in chuva.items() if not v.empty}
        nivel = {c: v for c, v in nivel.items() if not v.empty}
        if estacao not in nivel:
            raise SystemExit(f"sem leituras de nivel para {estacao}")
        X = montar_features(chuva, nivel, alvo=estacao)
        for h in HORIZONTES_H:
            r = avaliar_horizonte(X, alvo_deslocado(nivel[estacao], h), h)
            resultados.append(r)
            if salvar:
                registrar(s, est, r, datetime.now(UTC), obter_configuracao().pasta_artefatos)
    return resultados


def formatar(resultados: list[Resultado]) -> str:
    def f(v: float | None) -> str:
        return f"{v:6.1f}" if v is not None else "   n/d"

    linhas = [
        f"{'horiz.':>6} {'horas':>7} {'dias':>5} {'modelo':>7} {'persist.':>9} "
        f"{'tendenc.':>9}  decisao",
        "-" * 100,
    ]
    for r in resultados:
        decisao = "PUBLICADO" if r.publicar else "não publicado"
        linhas.append(
            f"{r.horizonte_h:>4} h {r.amostras:>7} {r.dias_uteis:>5.0f} {f(r.rmse_cm)} "
            f"{f(r.rmse_persistencia_cm):>9} {f(r.rmse_tendencia_cm):>9}  {decisao}: {r.motivo}"
        )
    linhas.append("\n(RMSE em cm da variacao do nivel; menor e melhor)")
    return "\n".join(linhas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--estacao", default=ALVO)
    ap.add_argument("--dias", type=int, default=120)
    ap.add_argument("--sem-salvar", action="store_true")
    args = ap.parse_args()
    configurar(obter_configuracao().log_level)
    pd.set_option("display.width", 200)
    print(formatar(treinar(args.estacao, args.dias, not args.sem_salvar)))
