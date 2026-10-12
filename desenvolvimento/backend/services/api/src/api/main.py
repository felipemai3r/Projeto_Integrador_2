"""API publica do sistema. Documentacao automatica em /docs."""

from typing import Annotated

from common.config import obter_configuracao
from common.logs import configurar
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import obter_sessao
from api.routers import chuva, estacoes

cfg = obter_configuracao()
configurar(cfg.log_level)

app = FastAPI(
    title="Sistema de apoio a decisão para enchentes, Presidente Getúlio",
    description="Estimativas de apoio. A fonte oficial é a Defesa Civil de Presidente Getúlio.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cfg.cors_origens.split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(estacoes.router)
api.include_router(chuva.router)


@api.get("/saude", tags=["operacao"])
def saude(s: Annotated[Session, Depends(obter_sessao)]) -> dict[str, str]:
    s.execute(text("select 1"))
    return {"status": "ok"}


app.include_router(api)
