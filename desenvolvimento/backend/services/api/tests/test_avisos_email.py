import re
from collections.abc import Iterator
from datetime import timedelta

import pytest
from common.enums import Faixa
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


# ---------- reinscricao de quem ja confirmou (nao pode desligar terceiro) ----------


def _confirmada(client: TestClient, caixa: CaixaFalsa, corpo: dict[str, str] = CORPO) -> None:
    client.post("/api/inscricoes/email", json=corpo)
    client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})


def _elegivel(base: Session, estacao: str = "DCSC-00043", faixa: Faixa = Faixa.ALERTA) -> int:
    base.expire_all()
    return len(avisos_email._elegiveis(base, _est_por_codigo(base, estacao), faixa))


def _est_por_codigo(s: Session, codigo: str) -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()


def test_reinscricao_de_confirmado_nao_desliga_os_avisos(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa)
    assert _elegivel(base) == 1
    r = client.post("/api/inscricoes/email", json={**CORPO, "faixa_minima": "extremo"})
    assert r.status_code == 202
    i = base.scalars(select(InscricaoEmail)).one()
    base.refresh(i)
    # continua ativa, com as preferencias de antes
    assert i.confirmada_em is not None and i.faixa_minima == "atencao"
    assert i.estacao_id == _est_por_codigo(base, "DCSC-00043").id
    assert _elegivel(base) == 1
    # o novo pedido espera de lado
    assert i.faixa_minima_pendente == "extremo" and i.token_hash_pendente is not None


def test_confirmar_o_link_novo_aplica_as_preferencias_pendentes(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa)
    client.post(
        "/api/inscricoes/email",
        json={"email": CORPO["email"], "estacao": "DCSC-00174", "faixa_minima": "alerta_alto"},
    )
    assert "mudar" in caixa.enviados[-1][1] or "mudança" in caixa.enviados[-1][1]
    r = client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})
    assert r.status_code == 200 and r.json()["status"] == "confirmado"
    i = base.scalars(select(InscricaoEmail)).one()
    base.refresh(i)
    assert i.faixa_minima == "alerta_alto"
    assert i.estacao_id == _est_por_codigo(base, "DCSC-00174").id
    assert i.confirmada_em is not None
    assert (i.token_hash_pendente, i.faixa_minima_pendente, i.estacao_id_pendente) == (
        None,
        None,
        None,
    )
    assert "ativados" in caixa.enviados[-1][1]
    assert _elegivel(base, "DCSC-00174", Faixa.ALERTA_ALTO) == 1
    assert _elegivel(base, "DCSC-00043", Faixa.EXTREMO) == 0  # nao e mais deste rio


def test_pedido_pendente_para_todos_os_rios_limpa_a_estacao(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa)
    client.post("/api/inscricoes/email", json={**CORPO, "estacao": None})
    client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})
    i = base.scalars(select(InscricaoEmail)).one()
    base.refresh(i)
    assert i.estacao_id is None and i.faixa_minima == "atencao"


def test_token_antigo_de_quem_ja_confirmou_nao_aplica_nada(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa)
    antigo = caixa.token("confirmar", 0)
    client.post("/api/inscricoes/email", json={**CORPO, "faixa_minima": "extremo"})
    r = client.post("/api/inscricoes/email/confirmar", json={"token": antigo})
    assert r.status_code == 200  # clicar de novo no link ja usado e inofensivo...
    i = base.scalars(select(InscricaoEmail)).one()
    base.refresh(i)
    assert i.faixa_minima == "atencao" and i.faixa_minima_pendente == "extremo"  # ...e nao aplica


def test_novo_pedido_invalida_o_pedido_pendente_anterior(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa)
    client.post("/api/inscricoes/email", json={**CORPO, "faixa_minima": "extremo"})
    primeiro = caixa.token("confirmar")
    client.post("/api/inscricoes/email", json={**CORPO, "faixa_minima": "alerta_alto"})
    r = client.post("/api/inscricoes/email/confirmar", json={"token": primeiro})
    assert r.status_code == 404  # o link do pedido anterior foi trocado pelo mais novo
    i = base.scalars(select(InscricaoEmail)).one()
    base.refresh(i)
    assert i.faixa_minima == "atencao"


def test_pedido_pendente_vence_em_48h(client: TestClient, base: Session, caixa: CaixaFalsa) -> None:
    _confirmada(client, caixa)
    client.post("/api/inscricoes/email", json={**CORPO, "faixa_minima": "extremo"})
    i = base.scalars(select(InscricaoEmail)).one()
    i.pendente_em = AGORA - timedelta(hours=49)
    base.commit()
    r = client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})
    assert r.status_code == 404
    base.refresh(i)
    assert i.faixa_minima == "atencao" and i.confirmada_em is not None


def test_resposta_e_identica_exista_ou_nao_o_email(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    nova = client.post("/api/inscricoes/email", json=CORPO)
    client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})
    de_confirmada = client.post("/api/inscricoes/email", json=CORPO)
    outra = client.post("/api/inscricoes/email", json={**CORPO, "email": "bia@exemplo.br"})
    pendente_de_novo = client.post(
        "/api/inscricoes/email", json={**CORPO, "email": "bia@exemplo.br"}
    )
    for r in (de_confirmada, outra, pendente_de_novo):
        assert (r.status_code, r.json()) == (nova.status_code, nova.json())


def test_falha_de_envio_tem_a_mesma_resposta_para_confirmada_e_nova(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa)
    base.commit()  # em producao, o commit da requisicao anterior
    caixa.ok = False
    a = client.post("/api/inscricoes/email", json=CORPO)
    b = client.post("/api/inscricoes/email", json={**CORPO, "email": "novo@exemplo.br"})
    assert (a.status_code, a.json()) == (b.status_code, b.json())
    base.rollback()  # o que `common.db.sessao` faz em producao quando a rota levanta erro
    i = base.scalars(select(InscricaoEmail).where(InscricaoEmail.email == "ana@exemplo.br")).one()
    base.refresh(i)
    assert i.confirmada_em is not None and i.token_hash_pendente is None  # nada ficou pela metade


def test_inscricao_nao_confirmada_renova_o_token_e_o_antigo_deixa_de_valer(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    client.post("/api/inscricoes/email", json=CORPO)
    antigo = caixa.token("confirmar")
    client.post("/api/inscricoes/email", json={**CORPO, "faixa_minima": "alerta_alto"})
    assert client.post("/api/inscricoes/email/confirmar", json={"token": antigo}).status_code == 404
    client.post("/api/inscricoes/email/confirmar", json={"token": caixa.token("confirmar")})
    i = base.scalars(select(InscricaoEmail)).one()
    base.refresh(i)
    assert i.confirmada_em is not None and i.faixa_minima == "alerta_alto"
    assert i.token_hash_pendente is None


def test_cancelar_continua_exigindo_o_link_assinado_do_dono(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa)
    client.post("/api/inscricoes/email", json={**CORPO, "faixa_minima": "extremo"})
    # nem o token de confirmacao (original ou pendente) nem um id adivinhado cancelam
    for token in (caixa.token("confirmar"), caixa.token("confirmar", 0), "1.", "1.abc", "x"):
        assert (
            client.post("/api/inscricoes/email/cancelar", json={"token": token}).status_code == 404
        )
    assert len(base.scalars(select(InscricaoEmail)).all()) == 1


def test_assinar_o_revolver_por_email_e_aceito_e_alerta_so_quem_e_dele(
    client: TestClient, base: Session, caixa: CaixaFalsa
) -> None:
    _confirmada(client, caixa, {**CORPO, "estacao": "DCSC-00174"})
    assert _elegivel(base, "DCSC-00174", Faixa.ALERTA) == 1
    assert _elegivel(base, "DCSC-00043", Faixa.ALERTA) == 0
    assert (
        client.post(
            "/api/inscricoes/email", json={**CORPO, "estacao": "DCSC-00021", "email": "z@x.br"}
        ).status_code
        == 422  # so estacao alvo
    )
