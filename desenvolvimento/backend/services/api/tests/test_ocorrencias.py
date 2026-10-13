import io
from datetime import timedelta
from pathlib import Path

import pytest
from common.config import obter_configuracao
from common.models import Leitura, Moderacao, Ocorrencia, Usuario
from common.seed import semear
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tempo_api import AGORA

from api.seguranca import criar_token, hash_senha

SEDE = {"latitude": "-27.0455", "longitude": "-49.6243"}
AGORA_ISO = (AGORA - timedelta(minutes=10)).isoformat()


def dados(**extra: str) -> dict[str, str]:
    base = {**SEDE, "ocorreu_em": AGORA_ISO, "tipo_impacto": "via_intransitavel"}
    base.update(extra)
    return base


@pytest.fixture
def base(s: Session, tmp_path: Path) -> Session:
    obter_configuracao().pasta_fotos = str(tmp_path)
    semear(s)
    s.commit()
    return s


def cabecalho(
    s: Session, papel: str = "moderador", email: str = "leo@exemplo.br"
) -> dict[str, str]:
    u = Usuario(nome="Leo", email=email, papel=papel, senha_hash=hash_senha("senha-forte-123"))
    s.add(u)
    s.commit()
    token, _ = criar_token(u, AGORA)
    return {"Authorization": f"Bearer {token}"}


def jpeg_com_exif() -> bytes:
    img = Image.new("RGB", (3000, 2000), "blue")
    exif = Image.Exif()
    exif[0x010F] = "FabricanteSecreto"  # Make
    exif[0x0110] = "ModeloSecreto"  # Model
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_registro_anonimo_entra_como_pendente(client: TestClient, base: Session) -> None:
    r = client.post("/api/ocorrencias", data=dados(descricao="  Água na rua  "))
    assert r.status_code == 201
    assert r.json()["status"] == "pendente"
    assert "Defesa Civil conferir" in r.json()["mensagem"]
    o = base.scalars(select(Ocorrencia)).one()
    assert o.descricao == "Água na rua" and o.status == "pendente"


def test_pendente_nao_aparece_no_mapa_publico(client: TestClient, base: Session) -> None:
    client.post("/api/ocorrencias", data=dados())
    assert client.get("/api/ocorrencias").json() == []


def test_ponto_fora_do_municipio_e_recusado(client: TestClient, base: Session) -> None:
    r = client.post("/api/ocorrencias", data=dados(latitude="-27.5900", longitude="-48.5500"))
    assert r.status_code == 422 and "dentro de Presidente Getúlio" in r.json()["detail"]


def test_data_futura_e_recusada(client: TestClient, base: Session) -> None:
    futuro = (AGORA + timedelta(hours=2)).isoformat()
    r = client.post("/api/ocorrencias", data=dados(ocorreu_em=futuro))
    assert r.status_code == 422 and "futuro" in r.json()["detail"]


def test_data_sem_fuso_e_data_muito_antiga_sao_recusadas(client: TestClient, base: Session) -> None:
    assert (
        client.post("/api/ocorrencias", data=dados(ocorreu_em="2026-10-12T10:00:00")).status_code
        == 422
    )
    antiga = (AGORA - timedelta(days=400)).isoformat()
    assert client.post("/api/ocorrencias", data=dados(ocorreu_em=antiga)).status_code == 422


def test_tipo_invalido_e_descricao_longa_sao_recusados(client: TestClient, base: Session) -> None:
    assert client.post("/api/ocorrencias", data=dados(tipo_impacto="meteoro")).status_code == 422
    assert client.post("/api/ocorrencias", data=dados(descricao="x" * 501)).status_code == 422


def test_limite_de_registros_por_hora(client: TestClient, base: Session) -> None:
    limite = obter_configuracao().limite_registros_hora
    for _ in range(limite):
        assert client.post("/api/ocorrencias", data=dados()).status_code == 201
    assert client.post("/api/ocorrencias", data=dados()).status_code == 429


def test_contexto_hidrologico_e_associado(client: TestClient, base: Session) -> None:
    from common.models import Estacao, Fonte

    est = base.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one()
    fonte = base.scalars(select(Fonte).where(Fonte.codigo == "dcsc_graphql")).one()
    quando = AGORA - timedelta(minutes=10)
    base.add(
        Leitura(
            estacao_id=est.id,
            variavel="nivel_m",
            valor=4.62,
            unidade="m",
            medido_em=quando - timedelta(minutes=2),
            fonte_id=fonte.id,
            qualidade="ok",
        )
    )
    base.commit()
    client.post("/api/ocorrencias", data=dados())
    o = base.scalars(select(Ocorrencia)).one()
    assert o.contexto["disponivel"] is True
    assert o.contexto["niveis"]["DCSC-00043"]["nivel_m"] == 4.62


def test_sem_dado_hidrologico_grava_mesmo_assim_e_avisa(client: TestClient, base: Session) -> None:
    antigo = (AGORA - timedelta(days=300)).isoformat()
    assert client.post("/api/ocorrencias", data=dados(ocorreu_em=antigo)).status_code == 201
    assert base.scalars(select(Ocorrencia)).one().contexto["disponivel"] is False


def test_foto_perde_exif_e_e_reduzida(client: TestClient, base: Session, tmp_path: Path) -> None:
    r = client.post(
        "/api/ocorrencias", data=dados(), files={"foto": ("a.jpg", jpeg_com_exif(), "image/jpeg")}
    )
    assert r.status_code == 201
    o = base.scalars(select(Ocorrencia)).one()
    arquivo = tmp_path / o.foto_path
    with Image.open(arquivo) as img:
        assert max(img.size) <= 1280
        assert len(img.getexif()) == 0  # nenhum metadado
    assert b"FabricanteSecreto" not in arquivo.read_bytes()
    assert b"ModeloSecreto" not in arquivo.read_bytes()


def test_arquivo_que_nao_e_foto_e_recusado(client: TestClient, base: Session) -> None:
    r = client.post(
        "/api/ocorrencias",
        data=dados(),
        files={"foto": ("a.jpg", b"isto nao e imagem", "image/jpeg")},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/ocorrencias", data=dados(), files={"foto": ("a.pdf", b"%PDF-1.4", "application/pdf")}
    )
    assert r.status_code == 422
    assert base.scalars(select(Ocorrencia)).all() == []


def test_foto_grande_demais_e_recusada(client: TestClient, base: Session) -> None:
    r = client.post(
        "/api/ocorrencias",
        data=dados(),
        files={"foto": ("a.jpg", b"0" * (5 * 1024 * 1024 + 1), "image/jpeg")},
    )
    assert r.status_code == 422 and "5 MB" in r.json()["detail"]


# ---------- moderacao ----------


def _registrar(client: TestClient) -> int:
    return client.post("/api/ocorrencias", data=dados()).json()["id"]


def test_moderacao_exige_login_e_papel(client: TestClient, base: Session) -> None:
    oid = _registrar(client)
    assert client.patch(f"/api/ocorrencias/{oid}", json={"acao": "validar"}).status_code == 401
    assert client.get("/api/ocorrencias", params={"status": "pendente"}).status_code == 401


def test_validar_publica_no_mapa_e_registra_historico(client: TestClient, base: Session) -> None:
    oid = _registrar(client)
    h = cabecalho(base)
    r = client.patch(f"/api/ocorrencias/{oid}", json={"acao": "validar"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "validada"
    publico = client.get("/api/ocorrencias").json()
    assert [o["id"] for o in publico] == [oid]
    assert publico[0]["moderado_por"] is None  # o publico nao ve quem moderou
    hist = client.get(f"/api/ocorrencias/{oid}/historico", headers=h).json()
    assert [(x["acao"], x["status_novo"], x["usuario"]) for x in hist] == [
        ("validar", "validada", "Leo")
    ]


def test_rejeitar_exige_motivo(client: TestClient, base: Session) -> None:
    oid = _registrar(client)
    h = cabecalho(base)
    assert (
        client.patch(f"/api/ocorrencias/{oid}", json={"acao": "rejeitar"}, headers=h).status_code
        == 422
    )
    r = client.patch(
        f"/api/ocorrencias/{oid}", json={"acao": "rejeitar", "nota": "Fora do local"}, headers=h
    )
    assert r.json()["status"] == "rejeitada"
    assert client.get("/api/ocorrencias").json() == []


def test_reclassificar_mantem_status_e_guarda_o_antes_e_o_depois(
    client: TestClient, base: Session
) -> None:
    oid = _registrar(client)
    h = cabecalho(base)
    r = client.patch(
        f"/api/ocorrencias/{oid}",
        json={"acao": "reclassificar", "tipo_impacto": "agua_imovel"},
        headers=h,
    )
    assert r.json()["tipo_impacto"] == "agua_imovel" and r.json()["status"] == "pendente"
    m = base.scalars(select(Moderacao)).one()
    assert (m.tipo_anterior, m.tipo_novo) == ("via_intransitavel", "agua_imovel")
    # reclassificar para o mesmo tipo nao faz sentido
    assert (
        client.patch(
            f"/api/ocorrencias/{oid}",
            json={"acao": "reclassificar", "tipo_impacto": "agua_imovel"},
            headers=h,
        ).status_code
        == 422
    )


def test_historico_acumula_varias_acoes(client: TestClient, base: Session) -> None:
    oid = _registrar(client)
    h = cabecalho(base)
    client.patch(f"/api/ocorrencias/{oid}", json={"acao": "validar"}, headers=h)
    client.patch(
        f"/api/ocorrencias/{oid}", json={"acao": "rejeitar", "nota": "Duplicado"}, headers=h
    )
    assert base.scalar(select(func.count()).select_from(Moderacao)) == 2


def test_foto_so_e_publica_depois_de_validada(client: TestClient, base: Session) -> None:
    client.post(
        "/api/ocorrencias", data=dados(), files={"foto": ("a.jpg", jpeg_com_exif(), "image/jpeg")}
    )
    oid = base.scalars(select(Ocorrencia.id)).one()
    assert client.get(f"/api/ocorrencias/{oid}/foto").status_code == 404
    h = cabecalho(base)
    assert client.get(f"/api/ocorrencias/{oid}/foto", headers=h).status_code == 200
    client.patch(f"/api/ocorrencias/{oid}", json={"acao": "validar"}, headers=h)
    r = client.get(f"/api/ocorrencias/{oid}/foto")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get("/api/ocorrencias").json()[0]["tem_foto"] is True


def test_ocorrencia_inexistente_da_404(client: TestClient, base: Session) -> None:
    h = cabecalho(base)
    assert (
        client.patch("/api/ocorrencias/999", json={"acao": "validar"}, headers=h).status_code == 404
    )
