import re
from collections.abc import Iterator
from datetime import timedelta

import pytest
from common.models import Alerta, Estacao, InscricaoEmail, NotificacaoEmail
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tempo_api import AGORA

from api import avisos_email
from api.main import app
from api.push import Resultado
from api.routers.avisos_email import obter_enviador


class CaixaFalsa:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.enviados: list[tuple[str, str, str]] = []

    def enviar(self, destino: str, assunto: str, texto: str) -> Resultado:
        self.enviados.append((destino, assunto, texto))
        return Resultado(self.ok, erro=None if self.ok else "falhou")

    def token(self, acao: str, n: int = -1) -> str:
        achado = re.search(rf"{acao}=([^\s]+)", self.enviados[n][2])
        assert achado, self.enviados[n][2]
        return achado.group(1)


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


@pytest.fixture
def caixa(client: TestClient) -> Iterator[CaixaFalsa]:
    c = CaixaFalsa()
    app.dependency_overrides[obter_enviador] = lambda: c
    yield c


CORPO = {"email": " Ana@Exemplo.br ", "estacao": "DCSC-00043", "faixa_minima": "atencao"}


def _est(s: Session) -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one()


def test_inscricao_fica_pendente_ate_confirmar(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    r = client.post("/api/inscricoes/email", json=CORPO)
    assert r.status_code == 202 and r.json()["status"] == "pendente"
    i = base.scalars(select(InscricaoEmail)).one()
    assert i.email == "ana@exemplo.br" and i.confirmada_em is None
    token = caixa.token("confirmar")
    assert token not in i.token_hash  # o banco so guarda o hash

    r = client.post("/api/inscricoes/email/confirmar", json={"token": token})
    assert r.status_code == 200 and r.json()["status"] == "confirmado"
    base.refresh(i)
    assert i.confirmada_em is not None
    assert "ativados" in caixa.enviados[-1][1]  # e-mail de boas-vindas com link de cancelar
    assert "cancelar=" in caixa.enviados[-1][2]


def test_token_errado_ou_vencido_nao_confirma(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    client.post("/api/inscricoes/email", json=CORPO)
    assert client.post("/api/inscricoes/email/confirmar", json={"token": "x"}).status_code == 404
    i = base.scalars(select(InscricaoEmail)).one()
    i.criada_em = AGORA - timedelta(hours=49)
    base.commit()
    r = client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})
    assert r.status_code == 404


def test_email_invalido_e_falha_de_envio(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    assert client.post("/api/inscricoes/email", json={**CORPO, "email": "ana"}).status_code == 422
    caixa.ok = False
    assert client.post("/api/inscricoes/email", json=CORPO).status_code == 503


def test_cancelar_apaga_tudo_e_link_assinado(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    client.post("/api/inscricoes/email", json=CORPO)
    client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})
    token = caixa.token("cancelar")
    forjado = token.split(".")[0] + ".0000"
    assert client.post("/api/inscricoes/email/cancelar", json={"token": forjado}).status_code == 404
    assert client.post("/api/inscricoes/email/cancelar", json={"token": token}).status_code == 200
    assert base.scalars(select(InscricaoEmail)).all() == []


def test_abertura_e_encerramento_so_para_confirmados(base: Session) -> None:
    est = _est(base)
    confirmada = InscricaoEmail(
        email="a@x.br", token_hash="h1", faixa_minima="atencao", confirmada_em=AGORA
    )
    pendente = InscricaoEmail(email="b@x.br", token_hash="h2", faixa_minima="atencao")
    so_alerta = InscricaoEmail(
        email="c@x.br", token_hash="h3", faixa_minima="alerta", confirmada_em=AGORA
    )
    base.add_all([confirmada, pendente, so_alerta])
    a = Alerta(
        estacao_id=est.id,
        faixa_anterior="normal",
        faixa_nova="atencao",
        severidade="atencao",
        origem="observado",
        criado_em=AGORA,
    )
    base.add(a)
    base.commit()

    caixa = CaixaFalsa()
    assert avisos_email.notificar_abertura(base, est, a, caixa, 4.6, "subindo") == 1
    destino, assunto, texto = caixa.enviados[0]
    assert destino == "a@x.br" and "atenção" in assunto
    assert "Observado" in texto and "Defesa Civil" in texto and "cancelar=" in texto

    a.encerrado_em = AGORA + timedelta(hours=2)
    base.commit()
    assert avisos_email.notificar_encerramento(base, est, a, caixa, 3.0) == 1
    assert "voltou ao normal" in caixa.enviados[-1][1]
    assert len(base.scalars(select(NotificacaoEmail)).all()) == 2
