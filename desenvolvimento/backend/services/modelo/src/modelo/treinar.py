"""Treina, valida e registra os modelos por horizonte (CDU12).

Uso: python -m modelo.treinar --estacao DCSC-00043 [--estacao DCSC-00174] [--desde 2025-09-13]
Sem --estacao treina todos os alvos (`modelo.features.ALVOS`), cada um isolado dos outros.
Roda sob demanda (e diariamente no servidor). Mostra a validacao contra os baselines e diz,
para cada horizonte, se foi publicado ou por que nao.

Janela de treino: POR ALVO (`ConfigAlvo.janela_dias`). Rio dos Indios (DCSC-00043) e Revolver
(DCSC-00174) usam todo o historico desde `INICIO_HISTORICO` (13/09/2025, inicio das series do
painel municipal); o 00043 ja nao depende de Boiteux/Ibirama, que so tem ~4 meses (ADR 0006).
`--dias N` (ultimos N dias) e `--desde AAAA-MM-DD` sobrescrevem o padrao de todos os alvos. A
janela so decide quantos dados entram: o criterio de publicacao (RN07, `treino.py`) nao muda.
"""

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from common.config import obter_configuracao
from common.db import sessao
from common.logs import configurar
from common.models import Estacao
from sqlalchemy import select

from modelo.dados import chuva_horaria, nivel_horario
from modelo.features import (
    ALVOS,
    HORIZONTES_H,
    alvo_deslocado,
    config_alvo,
    montar_features,
    pontos_chuva,
    vizinhos_nivel,
)
from modelo.registry import registrar
from modelo.treino import REGIMES, Resultado, avaliar_horizonte

log = logging.getLogger("modelo.treinar")

INICIO_HISTORICO = date(2025, 9, 13)
# Um ponto (chuva ou nivel vizinho) com menos que isso das horas da janela e deixado de fora das
# variaveis. Os pontos descartados aparecem no log e, como o artefato guarda a lista de colunas,
# a inferencia passa a nao exigi-los. (O modelo aceita NaN, mas um ponto que quase nao existe so
# acrescenta ruido; alem disso, treino.py descarta por dobra as colunas com < 50 valores.)
MIN_COBERTURA_PONTO = 0.5


class TreinoImpossivel(Exception):
    """O treino de um alvo nao pode rodar (estacao ou leituras ausentes)."""


def inicio_da_janela(
    fim: datetime,
    dias: int | None = None,
    desde: date | None = None,
    padrao_dias: int | None = None,
) -> datetime:
    """Inicio da janela. Precedencia: `dias`, `desde` (argumentos explicitos); depois o padrao do
    alvo (`padrao_dias` dias, ou todo o historico se None)."""
    if dias is None and desde is None:
        dias = padrao_dias
    if dias is not None:
        return fim - timedelta(days=dias)
    base = desde or INICIO_HISTORICO
    return datetime(base.year, base.month, base.day, tzinfo=UTC)


def cobertura(serie: pd.Series, inicio: datetime, fim: datetime) -> float:
    """Fracao das horas de [inicio, fim) com valor na serie."""
    horas = max(int((fim - inicio) / timedelta(hours=1)), 1)
    return float(serie.loc[(serie.index >= inicio) & (serie.index < fim)].notna().sum()) / horas


def manter_pontos_cobertos(
    series: dict[str, pd.Series],
    inicio: datetime,
    fim: datetime,
    minimo: float = MIN_COBERTURA_PONTO,
    obrigatorios: tuple[str, ...] = (),
) -> tuple[dict[str, pd.Series], dict[str, float]]:
    """Separa os pontos com cobertura suficiente. Devolve (mantidos, descartados -> cobertura).

    Pontos vazios sempre saem; `obrigatorios` (o proprio alvo) nunca sao descartados aqui.
    """
    mantidos: dict[str, pd.Series] = {}
    descartados: dict[str, float] = {}
    for cod, serie in series.items():
        c = cobertura(serie, inicio, fim) if not serie.empty else 0.0
        if (cod in obrigatorios and not serie.empty) or c >= minimo:
            mantidos[cod] = serie
        else:
            descartados[cod] = round(c, 3)
    return mantidos, descartados


def treinar(
    estacao: str, dias: int | None = None, salvar: bool = True, desde: date | None = None
) -> list[Resultado]:
    fim = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    inicio = inicio_da_janela(fim, dias, desde, config_alvo(estacao).janela_dias)
    resultados: list[Resultado] = []
    with sessao() as s:
        est = s.scalar(select(Estacao).where(Estacao.codigo == estacao))
        if est is None:
            raise TreinoImpossivel(f"estacao {estacao} nao encontrada")
        chuva = {c: chuva_horaria(s, c, inicio, fim) for c in pontos_chuva(estacao)}
        nivel = {c: nivel_horario(s, c, inicio, fim) for c in (estacao, *vizinhos_nivel(estacao))}
        chuva, sem_chuva = manter_pontos_cobertos(chuva, inicio, fim)
        nivel, sem_nivel = manter_pontos_cobertos(nivel, inicio, fim, obrigatorios=(estacao,))
        for descartados in (sem_chuva, sem_nivel):
            if descartados:
                log.warning(
                    "pontos fora do treino por cobertura baixa",
                    extra={"extra_campos": {"alvo": estacao, "cobertura": descartados}},
                )
        if estacao not in nivel:
            raise TreinoImpossivel(f"sem leituras de nivel para {estacao}")
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

    def largura(r: Resultado) -> str:
        """Largura total do intervalo (hi - lo, cm) em seco/chuva/chuva forte."""
        if not r.intervalo_por_regime:
            return "n/d"
        return "/".join(f"{hi - lo:.1f}" for lo, hi in (r.intervalo_por_regime[g] for g in REGIMES))

    linhas = [
        f"{'horiz.':>6} {'horas':>7} {'dias':>5} {'modelo':>7} {'persist.':>9} "
        f"{'tendenc.':>9} {'alfa':>6} {'cobert.':>8} {'largura seco/chuva/forte':>26}  decisao",
        "-" * 130,
    ]
    for r in resultados:
        decisao = "PUBLICADO" if r.publicar else "não publicado"
        alfa = f"{r.alfa_intervalo:.4g}" if r.alfa_intervalo is not None else "n/d"
        cobert = f"{r.cobertura_validacao:.1%}" if r.cobertura_validacao is not None else "n/d"
        linhas.append(
            f"{r.horizonte_h:>4} h {r.amostras:>7} {r.dias_uteis:>5.0f} {f(r.rmse_cm)} "
            f"{f(r.rmse_persistencia_cm):>9} {f(r.rmse_tendencia_cm):>9} {alfa:>6} {cobert:>8} "
            f"{largura(r):>26}  {decisao}: {r.motivo}"
        )
    linhas.append(
        "\n(RMSE em cm da variacao do nivel; menor e melhor. Largura = largura total do intervalo, "
        "em cm,\n por regime de chuva; cobert. = cobertura nos ultimos 40% dos residuos)"
    )
    return "\n".join(linhas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--estacao",
        action="append",
        help=f"estacao alvo (pode repetir); padrao: todas ({', '.join(ALVOS)})",
    )
    ap.add_argument("--dias", type=int, help="ultimos N dias (substitui o padrao de cada alvo)")
    ap.add_argument(
        "--desde",
        type=date.fromisoformat,
        help="treina desde AAAA-MM-DD (substitui o padrao de cada alvo)",
    )
    ap.add_argument("--sem-salvar", action="store_true")
    args = ap.parse_args()
    configurar(obter_configuracao().log_level)
    pd.set_option("display.width", 200)
    for alvo in args.estacao or list(ALVOS):
        print(f"\n=== {alvo} ===")
        try:
            print(formatar(treinar(alvo, args.dias, not args.sem_salvar, args.desde)))
        except TreinoImpossivel as e:
            print(f"não treinado: {e}")
