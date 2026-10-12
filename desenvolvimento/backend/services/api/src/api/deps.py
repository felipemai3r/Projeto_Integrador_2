from collections.abc import Iterator
from datetime import UTC, datetime

from common.db import sessao
from sqlalchemy.orm import Session


def obter_sessao() -> Iterator[Session]:
    with sessao() as s:
        yield s


def obter_agora() -> datetime:
    """Injetavel nos testes (relogio controlado)."""
    return datetime.now(UTC)
