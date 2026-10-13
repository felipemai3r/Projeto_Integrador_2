"""Carga de series horarias a partir das leituras. Sem vazamento de futuro: so agregacao passada.

Regras de qualidade (uma hora com cobertura baixa vira NaN, NUNCA zero):
- nivel: media das leituras da hora, exige ao menos 6 leituras (de ~12 esperadas em 5 min)
- chuva: soma dos incrementos de 5 min da hora, exige ao menos 9 de 12 (75%). Hora sem
  cobertura nao e "hora sem chuva": e hora desconhecida, e entra como NaN.
"""

from datetime import datetime

import pandas as pd
from common.models import Estacao, Leitura
from sqlalchemy import select
from sqlalchemy.orm import Session

MIN_LEITURAS_NIVEL = 6
MIN_LEITURAS_CHUVA = 9


def _serie_bruta(
    s: Session, codigo: str, variavel: str, inicio: datetime, fim: datetime
) -> pd.Series:
    linhas = s.execute(
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
    ).all()
    if not linhas:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    idx = pd.DatetimeIndex([t for t, _ in linhas], tz="UTC")
    return pd.Series([v for _, v in linhas], index=idx, dtype=float).sort_index()


def nivel_horario(s: Session, codigo: str, inicio: datetime, fim: datetime) -> pd.Series:
    """Nivel medio por hora (m). Horas com poucas leituras ficam NaN."""
    bruta = _serie_bruta(s, codigo, "nivel_m", inicio, fim)
    return horaria_media(bruta, MIN_LEITURAS_NIVEL)


def chuva_horaria(s: Session, codigo: str, inicio: datetime, fim: datetime) -> pd.Series:
    """Chuva por hora (mm) somando os incrementos de 5 min. Horas sem cobertura ficam NaN."""
    bruta = _serie_bruta(s, codigo, "chuva_acumulada_mm", inicio, fim)
    return horaria_soma(bruta, MIN_LEITURAS_CHUVA)


def horaria_media(bruta: pd.Series, minimo: int) -> pd.Series:
    if bruta.empty:
        return bruta
    g = bruta.resample("1h")
    return g.mean().where(g.count() >= minimo)


def horaria_soma(bruta: pd.Series, minimo: int) -> pd.Series:
    if bruta.empty:
        return bruta
    g = bruta.resample("1h")
    return g.sum(min_count=1).where(g.count() >= minimo)
