"""Fixtures compartilhadas: banco de teste PostgreSQL real, criado do zero pelas migracoes."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from common.models import Base

RAIZ = Path(__file__).resolve().parents[4]
URL_ADMIN = os.environ.get(
    "TEST_ADMIN_URL", "postgresql+psycopg://pgetulio:troque_esta_senha@localhost:5432/postgres"
)
NOME_BANCO = "pgetulio_test"


@pytest.fixture(scope="session")
def url_teste() -> str:
    admin = create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {NOME_BANCO} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {NOME_BANCO}"))
    admin.dispose()
    url = make_url(URL_ADMIN).set(database=NOME_BANCO).render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url
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
