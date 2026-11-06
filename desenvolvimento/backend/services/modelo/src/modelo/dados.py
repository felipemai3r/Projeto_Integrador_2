"""Carga de series horarias a partir das leituras. Sem vazamento de futuro: so agregacao passada.

Regras de qualidade (uma hora com cobertura baixa vira NaN, NUNCA zero):
- leituras do mesmo ponto vindas de fontes diferentes (GraphQL, painel municipal, REST), com
  segundos de diferenca, descrevem o MESMO instante: antes de contar ou agregar, fica uma
  leitura por intervalo de 5 min (media do intervalo). Sem isso 3 instantes distintos passariam
  por 6 leituras e a soma de incrementos dobraria (ver `uma_leitura_por_intervalo`).
- nivel: media da hora, exige ao menos 6 intervalos de 5 min com leitura (de 12 possiveis)
- chuva: soma dos incrementos de 5 min da hora, exige ao menos 9 de 12 intervalos (75%). Hora
  sem cobertura nao e "hora sem chuva": e hora desconhecida, e entra como NaN.
- chuva, fallback: onde nao ha incremento (a API estadual so retem ~80 dias; o painel municipal
  e o GraphQL trazem so a chuva acumulada na ultima hora, `chuva_h001_mm`, janela movel), a chuva
  da hora [H, H+1h) e a leitura h001 que FECHA essa hora (ver `horaria_h001`).
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from common.models import Estacao, Fonte, Leitura
from sqlalchemy import select
from sqlalchemy.orm import Session

MIN_LEITURAS_NIVEL = 6  # intervalos de 5 min distintos com leitura, nao leituras brutas
MIN_LEITURAS_CHUVA = 9
INTERVALO_LEITURA = "5min"  # cadencia das fontes; leituras no mesmo intervalo contam uma vez

# --- fallback h001 -------------------------------------------------------------------------
# A leitura h001 em T = chuva acumulada em [T-1h, T). Para a hora de rotulo H (chuva em
# [H, H+1h)) a leitura certa e a de T = H+1h. Aceita-se a mais tardia dentro de
# [H+1h-ANTES, H+1h+DEPOIS]:
# - ANTES = 5 min (um passo da cadencia): se a leitura exata falhou, a anterior ainda descreve
#   quase a mesma hora (janela deslocada em 5 min), em vez de perder a hora inteira;
# - DEPOIS = 1 min: so absorve o jitter de segundos do carimbo. Qualquer folga maior deixaria a
#   chuva de depois do fim da hora entrar na linha `t` (vazamento). Com 1 min o excesso e
#   desprezivel perante o atraso (horas) entre chover e o rio subir, e treino e inferencia usam
#   exatamente a mesma regra.
TOLERANCIA_H001_ANTES = timedelta(minutes=5)
TOLERANCIA_H001_DEPOIS = timedelta(minutes=1)
# Protecao contra pico espurio (ex.: h001 = 248 mm isolado). O h001 e uma soma em janela movel
# de 1 h: de uma leitura (5 min) para a seguinte ele sobe, no maximo, o que choveu naquele passo.
# Uma leitura mais de SALTO_MAX_H001_MM acima de TODAS as leituras anteriores ate 10 min antes
# dela nao e fisica (30 mm em 5 min equivalem a 360 mm/h, muito alem de qualquer registro) e e
# descartada. O criterio olha so para tras (causal): o mesmo resultado em serie completa e em
# serie cortada em qualquer instante, e nada de t+5 min entra na decisao. Sem anterior proxima
# (serie horaria, lacuna) nao ha como julgar e a leitura fica. O teto absoluto repete, por
# seguranca, o que o ingestor ja marca como suspeita.
SALTO_MAX_H001_MM = 30.0
VIZINHA_MAX_H001 = timedelta(minutes=10)
TETO_H001_MM = 150.0


# Fontes de chuva MEDIDA em pluviometro. `chuva_h001_mm` tambem existe vindo do Open-Meteo
# (reanalise ERA5 e previsao): e MODELO em grade, nao medicao, e nao pode entrar no lugar de
# uma leitura que faltou. Lista branca (nao lista negra): uma fonte nova so entra se alguem
# decidir que ela e medida.
FONTES_CHUVA_MEDIDA = ("dcsc_graphql", "dcsc_rest", "pdc_municipal")


def _serie_bruta(
    s: Session,
    codigo: str,
    variavel: str,
    inicio: datetime,
    fim: datetime,
    fontes: tuple[str, ...] | None = None,
) -> pd.Series:
    consulta = (
        select(Leitura.medido_em, Leitura.valor)
        .join(Estacao, Estacao.id == Leitura.estacao_id)
        .where(
            Estacao.codigo == codigo,
            Leitura.variavel == variavel,
            Leitura.qualidade == "ok",
            Leitura.valor.is_not(None),
            Leitura.medido_em >= inicio,
            Leitura.medido_em < fim,
        )
    )
    if fontes is not None:
        consulta = consulta.join(Fonte, Fonte.id == Leitura.fonte_id).where(
            Fonte.codigo.in_(fontes)
        )
    linhas = s.execute(consulta).all()
    if not linhas:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    idx = pd.DatetimeIndex([t for t, _ in linhas], tz="UTC")
    return pd.Series([v for _, v in linhas], index=idx, dtype=float).sort_index()


def nivel_horario(s: Session, codigo: str, inicio: datetime, fim: datetime) -> pd.Series:
    """Nivel medio por hora (m). Horas com poucas leituras ficam NaN."""
    bruta = _serie_bruta(s, codigo, "nivel_m", inicio, fim)
    return horaria_media(bruta, MIN_LEITURAS_NIVEL)


def chuva_horaria(s: Session, codigo: str, inicio: datetime, fim: datetime) -> pd.Series:
    """Chuva por hora (mm): soma dos incrementos de 5 min; onde nao ha cobertura, o h001 da fonte
    que so tem acumulado na ultima hora. Horas sem nenhuma das duas ficam NaN (nunca zero).

    A leitura que fecha a hora H esta em [H+1h-5min, H+1h+1min], por isso o h001 e buscado ate
    `fim` + tolerancia; so entram horas rotuladas em [inicio, fim).
    """
    incrementos = horaria_soma(
        _serie_bruta(s, codigo, "chuva_acumulada_mm", inicio, fim), MIN_LEITURAS_CHUVA
    )
    h001 = _serie_bruta(
        s,
        codigo,
        "chuva_h001_mm",
        inicio + timedelta(hours=1) - TOLERANCIA_H001_ANTES,
        fim + TOLERANCIA_H001_DEPOIS + timedelta(microseconds=1),
        fontes=FONTES_CHUVA_MEDIDA,
    )
    return combinar_chuva(incrementos, horaria_h001(h001, inicio, fim))


def uma_leitura_por_intervalo(bruta: pd.Series, intervalo: str = INTERVALO_LEITURA) -> pd.Series:
    """Uma leitura por intervalo (media dos valores que caem nele), rotulada no inicio do intervalo.

    Duas fontes gravando a mesma medida com segundos de diferenca viram uma so leitura, entao
    `count` mede instantes distintos (o minimo de cobertura volta a significar "6 instantes") e
    a soma de incrementos nao dobra. Com uma fonte so, em cadencia de 5 min, nada muda.
    """
    if bruta.empty:
        return bruta
    return bruta.groupby(bruta.index.floor(intervalo)).mean()


def horaria_media(bruta: pd.Series, minimo: int) -> pd.Series:
    if bruta.empty:
        return bruta
    g = uma_leitura_por_intervalo(bruta).resample("1h")
    return g.mean().where(g.count() >= minimo)


def horaria_soma(bruta: pd.Series, minimo: int) -> pd.Series:
    if bruta.empty:
        return bruta
    g = uma_leitura_por_intervalo(bruta).resample("1h")
    return g.sum(min_count=1).where(g.count() >= minimo)


def remover_picos_h001(bruta: pd.Series) -> pd.Series:
    """Descarta leituras h001 nao fisicas: acima do teto, ou um salto brusco sobre o passado.

    Salto brusco = leitura que supera em mais de SALTO_MAX_H001_MM o MAXIMO das leituras
    anteriores nos ultimos 10 min. Decide so com leituras passadas: `f(serie[:t])` e igual a
    `f(serie)[:t]` para qualquer corte, entao treino (serie completa) e inferencia (serie
    cortada no fim) filtram do mesmo jeito e nada de t+5 min vaza para a decisao.

    Compromisso (sem a leitura seguinte nao da para separar pico isolado de degrau): se o nivel
    do h001 pula de verdade e se mantem, so a PRIMEIRA leitura do degrau cai; a seguinte ja
    compara com a anterior alta e passa. Uma chuva forte real comeca subindo uns poucos mm por
    passo de 5 min, nunca mais de 30, entao a subida legitima nao e tocada. Conservador de
    proposito: sem anterior a ate 10 min (serie horaria, lacuna) a leitura passa.
    """
    if bruta.empty:
        return bruta
    bruta = bruta[(bruta >= 0) & (bruta <= TETO_H001_MM)].sort_index(kind="stable")
    if len(bruta) < 2:
        return bruta
    # maximo das anteriores em [t-10 min, t): NaN quando nao ha anterior proxima
    anterior = bruta.rolling(VIZINHA_MAX_H001, closed="left").max()
    with np.errstate(invalid="ignore"):
        pico = ((bruta - anterior) > SALTO_MAX_H001_MM).to_numpy()
    return bruta[~pico]


def horaria_h001(
    bruta: pd.Series,
    inicio: datetime | pd.Timestamp | None = None,
    fim: datetime | pd.Timestamp | None = None,
    antes: timedelta = TOLERANCIA_H001_ANTES,
    depois: timedelta = TOLERANCIA_H001_DEPOIS,
) -> pd.Series:
    """Chuva por hora (mm) a partir do h001: rotulo H = leitura que fecha a hora ([H, H+1h)).

    Para cada hora pega a leitura mais tardia em [H+1h-antes, H+1h+depois]; sem leitura nessa
    faixa a hora e NaN. Nunca olha alem de H+1h+depois, entao nao vaza futuro alem dessa folga.
    Leituras duplicadas no mesmo instante (fontes diferentes) viram a media. Picos espurios sao
    removidos antes (`remover_picos_h001`, so olhando para tras). `inicio`/`fim` limitam os
    rotulos a [inicio, fim).
    """
    vazia = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    if bruta.empty:
        return vazia
    bruta = remover_picos_h001(bruta.groupby(level=0).mean().sort_index())
    if bruta.empty:
        return vazia
    primeira = bruta.index[0].floor("1h") - pd.Timedelta(hours=1)
    ultima = bruta.index[-1].floor("1h")
    rotulos = pd.date_range(primeira, ultima, freq="1h", tz="UTC")
    if inicio is not None:
        rotulos = rotulos[rotulos >= pd.Timestamp(inicio)]
    if fim is not None:
        rotulos = rotulos[rotulos < pd.Timestamp(fim)]
    if len(rotulos) == 0:
        return vazia
    limite = rotulos + pd.Timedelta(hours=1) + depois  # leitura mais tardia aceita
    achadas = bruta.reindex(limite, method="ffill", tolerance=antes + depois)
    serie = pd.Series(achadas.to_numpy(), index=rotulos, dtype=float)
    if serie.notna().sum() == 0:
        return vazia
    return serie.loc[serie.first_valid_index() : serie.last_valid_index()]  # sem pontas vazias


def combinar_chuva(incrementos: pd.Series, h001: pd.Series) -> pd.Series:
    """Incremento onde houver cobertura; h001 so onde o incremento e NaN ou nao existe.

    O resultado cobre todas as horas entre a primeira e a ultima das duas series (indice
    horario regular: o `rolling` das variaveis conta linhas, entao nao pode ter buracos).
    """
    if incrementos.empty and h001.empty:
        return incrementos
    partes = [p for p in (incrementos, h001) if not p.empty]
    indice = pd.date_range(
        min(p.index.min() for p in partes), max(p.index.max() for p in partes), freq="1h"
    )
    base = incrementos.reindex(indice)
    return base.fillna(h001.reindex(indice)).rename(None)
