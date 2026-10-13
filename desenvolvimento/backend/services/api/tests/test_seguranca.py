import jwt
import pytest
from common.config import obter_configuracao
from common.models import Usuario
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.seguranca import criar_token, hash_senha, verificar_senha


def test_senha_certa_confere_e_errada_nao() -> None:
    h = hash_senha("uma-senha-longa-123")
    assert verificar_senha("uma-senha-longa-123", h)
    assert not verificar_senha("outra-senha-123", h)


def test_hash_nunca_guarda_a_senha_e_muda_a_cada_vez() -> None:
    a, b = hash_senha("mesma-senha-123"), hash_senha("mesma-senha-123")
    assert "mesma-senha" not in a
    assert a != b  # sal aleatorio


def test_hash_corrompido_nao_confere_nem_quebra() -> None:
    assert not verificar_senha("x", "lixo")
    assert not verificar_senha("x", "scrypt$a$b$c$d$e")


@pytest.fixture
def moderador(s: Session) -> Usuario:
    semear(s)
    u = Usuario(
        nome="Leo",
        email="leo@exemplo.br",
        papel="moderador",
        senha_hash=hash_senha("senha-forte-123"),
    )
    s.add(u)
    s.commit()
    return u


def test_login_correto_devolve_token_com_papel(client: TestClient, moderador: Usuario) -> None:
    r = client.post(
        "/api/auth/login", json={"email": " LEO@exemplo.br ", "senha": "senha-forte-123"}
    )
    assert r.status_code == 200
    corpo = r.json()
    dados = jwt.decode(corpo["token"], obter_configuracao().jwt_secret, algorithms=["HS256"])
    assert dados["sub"] == "leo@exemplo.br" and dados["papel"] == "moderador"
    assert corpo["nome"] == "Leo"


def test_login_errado_nao_revela_se_o_email_existe(client: TestClient, moderador: Usuario) -> None:
    a = client.post("/api/auth/login", json={"email": "leo@exemplo.br", "senha": "errada-errada"})
    b = client.post(
        "/api/auth/login", json={"email": "ninguem@exemplo.br", "senha": "errada-errada"}
    )
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_usuario_desativado_nao_entra(client: TestClient, moderador: Usuario, s: Session) -> None:
    moderador.ativo = False
    s.commit()
    r = client.post("/api/auth/login", json={"email": "leo@exemplo.br", "senha": "senha-forte-123"})
    assert r.status_code == 401


def test_login_tem_limite_de_tentativas(client: TestClient, moderador: Usuario) -> None:
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "leo@exemplo.br", "senha": "errada-errada"})
    r = client.post("/api/auth/login", json={"email": "leo@exemplo.br", "senha": "senha-forte-123"})
    assert r.status_code == 429


def test_token_adulterado_ou_expirado_e_recusado(client: TestClient, moderador: Usuario) -> None:
    from datetime import UTC, datetime, timedelta

    velho, _ = criar_token(moderador, datetime.now(UTC) - timedelta(days=2))
    r = client.get(
        "/api/ocorrencias",
        params={"status": "pendente"},
        headers={"Authorization": f"Bearer {velho}"},
    )
    assert r.status_code == 401
    r = client.get(
        "/api/ocorrencias", params={"status": "pendente"}, headers={"Authorization": "Bearer x.y.z"}
    )
    assert r.status_code == 401
