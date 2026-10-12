from collections.abc import Iterator

import pytest
from common.testing import s, url_teste  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tempo_api import AGORA

from api.deps import obter_agora, obter_sessao
from api.main import app


@pytest.fixture
def client(s: Session) -> Iterator[TestClient]:  # noqa: F811
    app.dependency_overrides[obter_sessao] = lambda: s
    app.dependency_overrides[obter_agora] = lambda: AGORA
    yield TestClient(app)
    app.dependency_overrides.clear()
