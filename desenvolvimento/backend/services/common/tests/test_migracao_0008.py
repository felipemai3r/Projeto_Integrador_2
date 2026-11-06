"""Migracao 0008 (preferencias pendentes do e-mail): segura com dados e reversivel."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from common.config import obter_configuracao
from common.db import obter_engine
from common.testing import NOME_BANCO, RAIZ, URL_ADMIN

BANCO = f"{NOME_BANCO}_mig"


@pytest.fixture
def banco_da_migracao() -> Iterator[str]:
    """Banco proprio, para nao mexer no banco dos demais testes."""
    admin = create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {BANCO} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {BANCO}"))
    url = make_url(URL_ADMIN).set(database=BANCO).render_as_string(hide_password=False)
    anterior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    obter_configuracao.cache_clear()
    obter_engine.cache_clear()
    try:
        yield url
    finally:
        if anterior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = anterior
        obter_configuracao.cache_clear()
        obter_engine.cache_clear()
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {BANCO} WITH (FORCE)"))
        admin.dispose()


def _cfg() -> Config:
    cfg = Config(str(RAIZ / "db" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "db" / "migrations"))
    return cfg


def _colunas(url: str) -> set[str]:
    eng = create_engine(url)
    try:
        return {c["name"] for c in inspect(eng).get_columns("inscricao_email")}
    finally:
        eng.dispose()


def test_sobe_e_desce_sem_perder_a_inscricao_confirmada(banco_da_migracao: str) -> None:
    url = banco_da_migracao
    command.upgrade(_cfg(), "0007")
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(
            text(
                "insert into inscricao_email (email, token_hash, faixa_minima, confirmada_em) "
                "values ('a@x.br', 'h1', 'alerta', now())"
            )
        )
    assert "token_hash_pendente" not in _colunas(url)

    command.upgrade(_cfg(), "0008")
    novas = {"token_hash_pendente", "estacao_id_pendente", "faixa_minima_pendente", "pendente_em"}
    assert novas <= _colunas(url)
    with eng.begin() as c:
        linha = c.execute(
            text(
                "select faixa_minima, confirmada_em is not null, token_hash_pendente "
                "from inscricao_email"
            )
        ).one()
        assert tuple(linha) == ("alerta", True, None)  # existente: ativa e sem pedido pendente
        c.execute(
            text(
                "update inscricao_email set token_hash_pendente='h2', "
                "faixa_minima_pendente='atencao'"
            )
        )

    command.downgrade(_cfg(), "0007")
    assert not (novas & _colunas(url))
    with eng.connect() as c:
        linha = c.execute(
            text("select faixa_minima, confirmada_em is not null from inscricao_email")
        ).one()
    assert tuple(linha) == ("alerta", True)  # preferencias vigentes intactas
    command.upgrade(_cfg(), "0008")  # e sobe de novo
    eng.dispose()
