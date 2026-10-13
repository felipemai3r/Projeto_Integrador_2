"""API publica do sistema. Documentacao automatica em /docs."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from common.config import obter_configuracao
from common.logs import configurar
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api import avaliador
from api.deps import obter_sessao
from api.routers import (
    alertas,
    auth,
    chuva,
    correlacao,
    estacoes,
    inscricoes,
    municipio,
    ocorrencias,
)

cfg = obter_configuracao()
configurar(cfg.log_level)


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    sch = avaliador.iniciar() if cfg.avaliador_ativo else None
    yield
    if sch is not None:
        sch.shutdown(wait=False)


app = FastAPI(
    lifespan=ciclo_de_vida,
    title="Sistema de apoio a decisão para enchentes, Presidente Getúlio",
    description="Estimativas de apoio. A fonte oficial é a Defesa Civil de Presidente Getúlio.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cfg.cors_origens.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(estacoes.router)
api.include_router(alertas.router)
api.include_router(auth.router)
api.include_router(inscricoes.router)
api.include_router(municipio.router)
api.include_router(ocorrencias.router)
api.include_router(chuva.router)
api.include_router(correlacao.router)


@api.get("/saude", tags=["operacao"])
def saude(s: Annotated[Session, Depends(obter_sessao)]) -> dict[str, str]:
    s.execute(text("select 1"))
    return {"status": "ok"}


app.include_router(api)
