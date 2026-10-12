"""Engine e sessao do SQLAlchemy."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from common.config import obter_configuracao


@lru_cache
def obter_engine() -> Engine:
    return create_engine(obter_configuracao().database_url, pool_pre_ping=True)


@contextmanager
def sessao() -> Iterator[Session]:
    """Sessao com commit ao sair e rollback em excecao."""
    with sessionmaker(obter_engine(), expire_on_commit=False)() as s:
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
