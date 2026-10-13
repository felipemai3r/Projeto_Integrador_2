"""Registro e versionamento de modelos (secao 6.4 da arquitetura).

Cada treino grava uma linha em `modelo` (inclusive os NAO publicados, com o motivo: a falta de
modelo e informacao). So um modelo por estacao e horizonte fica com `publicado = true`.
Rollback e trocar a flag. O artefato (joblib) fica em volume compartilhado com a API.
"""

from datetime import datetime
from pathlib import Path

import joblib
from common.models import Estacao, Modelo
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from modelo.treino import Resultado

ALGORITMO = "ridge"


def registrar(
    s: Session, estacao: Estacao, r: Resultado, treinado_em: datetime, pasta: str
) -> Modelo:
    publicado = bool(r.publicar and r.pipeline is not None)
    if publicado:
        s.execute(
            update(Modelo)
            .where(Modelo.estacao_id == estacao.id, Modelo.horizonte_h == r.horizonte_h)
            .values(publicado=False)
        )
    m = Modelo(
        estacao_id=estacao.id,
        horizonte_h=r.horizonte_h,
        algoritmo=ALGORITMO,
        treinado_em=treinado_em,
        amostras=r.amostras,
        rmse_cm=r.rmse_cm or 0.0,
        mae_cm=r.mae_cm or 0.0,
        rmse_persistencia_cm=r.rmse_persistencia_cm or 0.0,
        publicado=publicado,
        caminho_artefato="",
        metadados={
            "motivo": r.motivo,
            "dias_uteis": r.dias_uteis,
            "colunas": r.colunas,
            "rmse_tendencia_cm": r.rmse_tendencia_cm,
            "desvio_residual_cm": r.desvio_residual_cm,
        },
    )
    s.add(m)
    s.flush()
    if publicado:
        destino = Path(pasta) / estacao.codigo / str(r.horizonte_h)
        destino.mkdir(parents=True, exist_ok=True)
        caminho = destino / f"{m.id}.joblib"
        joblib.dump(
            {"pipeline": r.pipeline, "colunas": r.colunas, "faixa_treino": r.faixa_treino}, caminho
        )
        m.caminho_artefato = str(caminho)
    return m


def publicados(s: Session, estacao_id: int) -> dict[int, Modelo]:
    linhas = s.scalars(select(Modelo).where(Modelo.estacao_id == estacao_id, Modelo.publicado))
    return {m.horizonte_h: m for m in linhas}


def ultimos_treinos(s: Session, estacao_id: int) -> dict[int, Modelo]:
    """O treino mais recente de cada horizonte, publicado ou nao (para explicar a ausencia)."""
    vistos: dict[int, Modelo] = {}
    for m in s.scalars(
        select(Modelo)
        .where(Modelo.estacao_id == estacao_id)
        .order_by(Modelo.treinado_em.desc(), Modelo.id.desc())
    ):
        vistos.setdefault(m.horizonte_h, m)
    return vistos


def carregar_artefato(caminho: str) -> dict:
    return joblib.load(caminho)
