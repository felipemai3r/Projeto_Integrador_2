from datetime import datetime, timedelta

import pytest
from common.models import Alerta, Estacao, Fonte, Inscricao, Leitura, Notificacao
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tempo_api import AGORA

from api.avaliador import _notificar
from api.push import Resultado, notificar_abertura, notificar_encerramento

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {"p256dh": "chave-p256dh", "auth": "chave-auth"}


class EnviadorFalso:
    """Registra o que seria enviado. `respostas` define o resultado por endpoint."""

    def __init__(self, respostas: dict[str, Resultado] | None = None) -> None:
        self.enviados: list[tuple[str, dict[str, str]]] = []
        self.respostas = respostas or {}

    def enviar(self, inscricao: Inscricao, payload: dict[str, str]) -> Resultado:
        self.enviados.append((inscricao.endpoint, payload))
        return self.respostas.get(inscricao.endpoint, Resultado(True))


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def _est(s: Session, codigo: str = "DCSC-00043") -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()


def _insc(
    s: Session, nome: str, faixa: str = "atencao", estacao: str | None = "DCSC-00043"
) -> Inscricao:
    i = Inscricao(
        endpoint=f"https://fcm.googleapis.com/fcm/send/{nome}",
        chave_p256dh="k",
        chave_auth="a",
        faixa_minima=faixa,
        estacao_id=_est(s, estacao).id if estacao else None,
    )
    s.add(i)
    s.commit()
    return i


def _alerta(s: Session, de: str, para: str, origem: str = "observado") -> Alerta:
    a = Alerta(
        estacao_id=_est(s).id,
        faixa_anterior=de,
        faixa_nova=para,
        severidade=para,
        origem=origem,
        criado_em=AGORA,
    )
    s.add(a)
    s.commit()
    return a


# ---------- inscricao via API ----------


def test_inscrever_e_atualizar_preferencias(client: TestClient, base: Session) -> None:
    corpo = {"endpoint": ENDPOINT, "keys": KEYS, "estacao": "DCSC-00043", "faixa_minima": "atencao"}
    assert client.post("/api/inscricoes", json=corpo).status_code == 201
    corpo["faixa_minima"] = "alerta"
    assert client.post("/api/inscricoes", json=corpo).status_code == 201
    linhas = base.scalars(select(Inscricao)).all()
    assert len(linhas) == 1 and linhas[0].faixa_minima == "alerta" and linhas[0].ativa


def test_endpoint_fora_dos_servicos_de_push_e_recusado_ssrf(
    client: TestClient, base: Session
) -> None:
    for url in (
        "http://fcm.googleapis.com/x",  # sem https
        "https://evil.example.com/x",
        "https://169.254.169.254/latest/meta-data",
        "https://localhost/x",
        "https://fcm.googleapis.com.evil.com/x",  # sufixo enganoso
        "https://fcm.googleapis.com:8443/x",
    ):
        r = client.post(
            "/api/inscricoes", json={"endpoint": url, "keys": KEYS, "faixa_minima": "atencao"}
        )
        assert r.status_code == 422, url
    assert base.scalars(select(Inscricao)).all() == []


def test_faixa_ou_estacao_invalida_e_recusada(client: TestClient, base: Session) -> None:
    ruim = {"endpoint": ENDPOINT, "keys": KEYS}
    assert (
        client.post("/api/inscricoes", json={**ruim, "faixa_minima": "normal"}).status_code == 422
    )
    assert (
        client.post(
            "/api/inscricoes", json={**ruim, "faixa_minima": "atencao", "estacao": "DCSC-00021"}
        ).status_code
        == 422
    )


def test_cancelar_apaga_inscricao_e_historico_de_envios(client: TestClient, base: Session) -> None:
    i = _insc(base, "x")
    a = _alerta(base, "normal", "atencao")
    notificar_abertura(base, _est(base), a, EnviadorFalso())
    base.commit()
    assert base.scalars(select(Notificacao)).all()
    r = client.request("DELETE", "/api/inscricoes", json={"endpoint": i.endpoint})
    assert r.status_code == 200
    assert (
        base.scalars(select(Inscricao)).all() == []
        and base.scalars(select(Notificacao)).all() == []
    )
    # idempotente
    assert (
        client.request("DELETE", "/api/inscricoes", json={"endpoint": i.endpoint}).status_code
        == 200
    )


def test_chave_publica_informa_se_esta_configurada(client: TestClient) -> None:
    assert set(client.get("/api/push/chave").json()) == {"configurado", "chave_publica"}


# ---------- envio ----------


def test_so_recebe_quem_tem_estacao_e_faixa_minima_compativeis(base: Session) -> None:
    _insc(base, "atencao")  # minimo atencao
    _insc(base, "alerta", faixa="alerta")  # so quer alerta
    _insc(base, "observacao", faixa="observacao")
    _insc(base, "todas", estacao=None)  # todas as estacoes
    _insc(base, "outra", estacao="DCSC-00174")  # outra estacao
    env = EnviadorFalso()
    n = notificar_abertura(base, _est(base), _alerta(base, "normal", "atencao"), env)
    assert sorted(e.rsplit("/", 1)[1] for e, _ in env.enviados) == [
        "atencao",
        "observacao",
        "todas",
    ]
    assert n == 3


def test_alerta_maximo_chega_a_quem_pediu_so_alerta(base: Session) -> None:
    _insc(base, "alerta", faixa="alerta")
    env = EnviadorFalso()
    notificar_abertura(base, _est(base), _alerta(base, "atencao", "alerta"), env)
    assert len(env.enviados) == 1


def test_texto_diz_origem_nivel_e_fonte_oficial(base: Session) -> None:
    _insc(base, "a")
    env = EnviadorFalso()
    notificar_abertura(base, _est(base), _alerta(base, "normal", "atencao"), env, 4.62, "subindo")
    payload = env.enviados[0][1]
    assert payload["titulo"] == "Rio dos Índios em atenção"
    assert (
        payload["corpo"]
        == "Nível em 4,62 m, subindo. Observado. Fonte oficial: Defesa Civil de Presidente Getúlio."
    )
    assert len(payload["titulo"]) <= 50


def test_previsao_e_rotulada_como_previsao(base: Session) -> None:
    _insc(base, "a")
    env = EnviadorFalso()
    notificar_abertura(
        base, _est(base), _alerta(base, "normal", "atencao", origem="previsto"), env, 4.2
    )
    assert "Previsão." in env.enviados[0][1]["corpo"]


def test_inscricao_expirada_410_e_desativada(base: Session) -> None:
    i = _insc(base, "morta")
    env = EnviadorFalso({i.endpoint: Resultado(False, expirada=True, erro="HTTP 410")})
    n = notificar_abertura(base, _est(base), _alerta(base, "normal", "atencao"), env)
    base.commit()
    assert n == 0
    base.refresh(i)
    assert i.ativa is False
    assert base.scalars(select(Notificacao)).one().status == "expirada"
    # e nao recebe mais
    env2 = EnviadorFalso()
    notificar_abertura(base, _est(base), _alerta(base, "atencao", "alerta"), env2)
    assert env2.enviados == []


def test_falha_de_um_destinatario_nao_impede_os_outros(base: Session) -> None:
    ruim = _insc(base, "ruim")
    _insc(base, "boa")
    env = EnviadorFalso({ruim.endpoint: Resultado(False, erro="timeout")})
    n = notificar_abertura(base, _est(base), _alerta(base, "normal", "atencao"), env)
    base.commit()
    assert n == 1
    status = {x.status for x in base.scalars(select(Notificacao))}
    assert status == {"enviada", "falha"}
    assert (
        base.scalars(select(Inscricao).where(Inscricao.id == ruim.id)).one().ativa
    )  # falha temporaria nao desativa


def test_encerramento_so_para_quem_recebeu_a_abertura(base: Session) -> None:
    recebeu = _insc(base, "recebeu")
    _insc(
        base, "nao-recebeu", faixa="alerta"
    )  # so queria alerta: nao recebeu a abertura de atencao
    abertura = _alerta(base, "normal", "atencao")
    notificar_abertura(base, _est(base), abertura, EnviadorFalso())
    abertura.encerrado_em = AGORA + timedelta(hours=1)
    base.commit()
    env = EnviadorFalso()
    n = notificar_encerramento(base, _est(base), abertura, env, 3.1)
    assert n == 1 and env.enviados[0][0] == recebeu.endpoint
    assert env.enviados[0][1]["titulo"] == "Rio dos Índios voltou ao normal"
    assert "3,10 m" in env.enviados[0][1]["corpo"]


# ---------- integracao com a regra de subida (RN02) ----------


def _nivel(s: Session, valor: float, quando: datetime) -> None:
    fonte = s.scalars(select(Fonte).where(Fonte.codigo == "dcsc_graphql")).one()
    s.add(
        Leitura(
            estacao_id=_est(s).id,
            variavel="nivel_m",
            valor=valor,
            unidade="m",
            medido_em=quando,
            fonte_id=fonte.id,
            qualidade="ok",
        )
    )
    s.commit()


def test_descida_para_faixa_ainda_nao_normal_nao_gera_push(base: Session) -> None:
    _insc(base, "a")
    _nivel(base, 4.6, AGORA)
    desce = Alerta(
        estacao_id=_est(base).id,
        faixa_anterior="alerta",
        faixa_nova="atencao",
        severidade="atencao",
        origem="observado",
        criado_em=AGORA,
    )
    base.add(desce)
    base.commit()
    env = EnviadorFalso()
    _notificar(base, _est(base), "atencao", desce, env)
    assert env.enviados == []


def test_subida_gera_push_com_nivel_real(base: Session) -> None:
    _insc(base, "a")
    _nivel(base, 4.62, AGORA)
    a = _alerta(base, "normal", "atencao")
    env = EnviadorFalso()
    _notificar(base, _est(base), "atencao", a, env)
    assert len(env.enviados) == 1 and "4,62 m" in env.enviados[0][1]["corpo"]


def test_erro_inesperado_no_envio_nao_derruba_o_avaliador(base: Session) -> None:
    class Quebrado:
        def enviar(self, inscricao: Inscricao, payload: dict[str, str]) -> Resultado:
            raise RuntimeError("boom")

    _insc(base, "a")
    _nivel(base, 4.62, AGORA)
    a = _alerta(base, "normal", "atencao")
    _notificar(base, _est(base), "atencao", a, Quebrado())  # nao levanta


def test_sem_chaves_vapid_nao_envia_e_diz_por_que(
    base: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from common.config import obter_configuracao

    from api.push import EnviadorWebPush

    monkeypatch.setattr(obter_configuracao(), "vapid_private_key", "")  # independe do .env

    i = _insc(base, "a")
    r = EnviadorWebPush().enviar(i, {"titulo": "t", "corpo": "c", "url": "u", "tag": "x"})
    assert r.ok is False and "VAPID" in (r.erro or "")
