"""Fixtures compartilhadas: banco de teste PostgreSQL real, criado do zero pelas migracoes."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from common.config import obter_configuracao
from common.db import obter_engine
from common.models import Base

RAIZ = Path(__file__).resolve().parents[4]
URL_ADMIN = os.environ.get(
    "TEST_ADMIN_URL", "postgresql+psycopg://pgetulio:troque_esta_senha@localhost:5432/postgres"
)
# TEST_DB_NAME permite duas suites em paralelo sem uma derrubar o banco da outra
NOME_BANCO = os.environ.get("TEST_DB_NAME", "pgetulio_test")
if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", NOME_BANCO):
    raise ValueError(f"TEST_DB_NAME invalido: {NOME_BANCO!r}")


@pytest.fixture(scope="session")
def url_teste() -> str:
    admin = create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {NOME_BANCO} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {NOME_BANCO}"))
    admin.dispose()
    url = make_url(URL_ADMIN).set(database=NOME_BANCO).render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url
    # a configuracao pode ja ter sido lida (import de app) apontando para o banco real
    obter_configuracao.cache_clear()
    obter_engine.cache_clear()
    cfg = Config(str(RAIZ / "db" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "db" / "migrations"))
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
def s(url_teste: str) -> Iterator[Session]:
    engine = create_engine(url_teste)
    with Session(engine) as sessao:
        yield sessao
        sessao.rollback()
        for tabela in reversed(Base.metadata.sorted_tables):
            sessao.execute(text(f'TRUNCATE "{tabela.name}" RESTART IDENTITY CASCADE'))
        sessao.commit()
    engine.dispose()
