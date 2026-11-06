"""Utilitarios de borda da API: limite de taxa, IP do cliente, tratamento de foto e contexto."""

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from common.config import obter_configuracao
from common.models import Estacao, Fonte, Leitura, Usuario
from common.seed import semear
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from api.contexto import MIN_LEITURAS_CHUVA_24H, TOLERANCIA_NIVEL, contexto_hidrologico
from api.fotos import LADO_MAX, TAMANHO_MAX, FotoInvalida, tratar_e_salvar
from api.limite import LimiteTaxa, exigir, ip_do_cliente
from api.seguranca import hash_senha

T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


# ---------- LimiteTaxa ----------


def test_permite_ate_o_maximo_e_recusa_a_proxima() -> None:
    lim = LimiteTaxa(3, timedelta(minutes=10))
    assert [lim.permitir("a", T0) for _ in range(4)] == [True, True, True, False]


def test_recusa_nao_consome_cota() -> None:
    lim = LimiteTaxa(1, timedelta(minutes=10))
    lim.permitir("a", T0)
    for _ in range(5):
        assert lim.permitir("a", T0 + timedelta(minutes=5)) is False
    # liberou no instante exato em que o unico evento aceito sai da janela (+ 1 s)
    assert lim.permitir("a", T0 + timedelta(minutes=10, seconds=1)) is True


def test_evento_na_borda_exata_da_janela_ainda_conta() -> None:
    lim = LimiteTaxa(1, timedelta(minutes=10))
    lim.permitir("a", T0)
    assert lim.permitir("a", T0 + timedelta(minutes=10)) is False  # == janela: ainda dentro
    assert lim.permitir("a", T0 + timedelta(minutes=10, microseconds=1)) is True


def test_chaves_diferentes_tem_cotas_separadas() -> None:
    lim = LimiteTaxa(1, timedelta(hours=1))
    assert lim.permitir("1.1.1.1", T0) and lim.permitir("2.2.2.2", T0)
    assert not lim.permitir("1.1.1.1", T0)


def test_janela_deslizante_libera_um_por_vez() -> None:
    lim = LimiteTaxa(2, timedelta(minutes=10))
    lim.permitir("a", T0)
    lim.permitir("a", T0 + timedelta(minutes=6))
    assert not lim.permitir("a", T0 + timedelta(minutes=9))
    assert lim.permitir("a", T0 + timedelta(minutes=11))  # saiu o primeiro, nao o segundo
    assert not lim.permitir("a", T0 + timedelta(minutes=12))


def test_limpar_zera_todas_as_chaves() -> None:
    lim = LimiteTaxa(1, timedelta(hours=1))
    lim.permitir("a", T0)
    lim.limpar()
    assert lim.permitir("a", T0) is True


def test_exigir_levanta_429_em_portugues_quando_estoura() -> None:
    lim = LimiteTaxa(1, timedelta(hours=1))
    exigir(lim, "a", T0)
    with pytest.raises(HTTPException) as e:
        exigir(lim, "a", T0)
    assert e.value.status_code == 429 and "Muitas tentativas" in e.value.detail


# ---------- ip_do_cliente ----------


def requisicao(cabecalhos: dict[str, str], cliente: tuple[str, int] | None) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in cabecalhos.items()],
            "client": cliente,
        }
    )


def test_ip_vem_do_primeiro_valor_do_x_forwarded_for() -> None:
    req = requisicao({"X-Forwarded-For": " 203.0.113.9 , 10.0.0.1, 10.0.0.2"}, ("10.0.0.2", 1))
    assert ip_do_cliente(req) == "203.0.113.9"


def test_sem_cabecalho_usa_o_endereco_da_conexao() -> None:
    assert ip_do_cliente(requisicao({}, ("198.51.100.7", 4000))) == "198.51.100.7"


def test_sem_cabecalho_e_sem_cliente_cai_em_desconhecido() -> None:
    assert ip_do_cliente(requisicao({}, None)) == "desconhecido"


# ---------- fotos ----------


def imagem(tamanho: tuple[int, int], formato: str = "JPEG", exif: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", tamanho, (30, 90, 160))
    kw = {"exif": exif} if exif is not None else {}
    img.save(buf, formato, **kw)
    return buf.getvalue()


def test_tipos_aceitos_sao_so_jpeg_png_e_webp(tmp_path: Path) -> None:
    for tipo in ("image/gif", "application/pdf", "text/html", None, ""):
        with pytest.raises(FotoInvalida, match="JPEG, PNG ou WebP"):
            tratar_e_salvar(imagem((10, 10)), tipo, str(tmp_path))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("formato", "tipo"), [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_cada_formato_aceito_vira_jpeg_com_nome_gerado_pelo_servidor(
    tmp_path: Path, formato: str, tipo: str
) -> None:
    nome = tratar_e_salvar(imagem((40, 30), formato), tipo, str(tmp_path))
    assert nome.endswith(".jpg") and len(nome) == 36  # uuid4 hex + .jpg
    with Image.open(tmp_path / nome) as saida:
        assert saida.format == "JPEG"


def test_foto_no_limite_de_5_mb_passa_no_tamanho_e_acima_e_recusada(tmp_path: Path) -> None:
    with pytest.raises(FotoInvalida, match="5 MB"):
        tratar_e_salvar(b"0" * (TAMANHO_MAX + 1), "image/jpeg", str(tmp_path))
    # exatamente no limite passa pela checagem de tamanho e cai na de conteudo
    with pytest.raises(FotoInvalida, match="Não conseguimos ler"):
        tratar_e_salvar(b"0" * TAMANHO_MAX, "image/jpeg", str(tmp_path))


def test_conteudo_que_nao_e_imagem_mesmo_com_tipo_correto_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(FotoInvalida, match="Não conseguimos ler"):
        tratar_e_salvar(b"<html>nao sou foto</html>", "image/png", str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_imagem_truncada_e_recusada_sem_deixar_arquivo(tmp_path: Path) -> None:
    corte = imagem((300, 300))[:200]
    with pytest.raises(FotoInvalida):
        tratar_e_salvar(corte, "image/jpeg", str(tmp_path))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("entrada", "saida"),
    [((4000, 2000), (1280, 640)), ((2000, 4000), (640, 1280)), ((800, 600), (800, 600))],
)
def test_reduz_pelo_maior_lado_e_nunca_amplia(
    tmp_path: Path, entrada: tuple[int, int], saida: tuple[int, int]
) -> None:
    nome = tratar_e_salvar(imagem(entrada), "image/jpeg", str(tmp_path))
    with Image.open(tmp_path / nome) as img:
        assert img.size == saida and max(img.size) <= LADO_MAX


def test_metadados_exif_com_gps_nao_acompanham_a_foto(tmp_path: Path) -> None:
    exif = Image.Exif()
    exif[0x010F] = "FabricanteSecreto"  # Make
    exif[0x8825] = {1: "S", 2: (27.0, 2.0, 43.0)}  # ponteiro GPS
    nome = tratar_e_salvar(imagem((50, 50), exif=exif.tobytes()), "image/jpeg", str(tmp_path))
    bytes_saida = (tmp_path / nome).read_bytes()
    assert b"FabricanteSecreto" not in bytes_saida
    with Image.open(tmp_path / nome) as img:
        assert len(img.getexif()) == 0


def test_rotacao_do_exif_e_aplicada_antes_de_descartar_os_metadados(tmp_path: Path) -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # orientacao: girar 90 graus
    nome = tratar_e_salvar(imagem((60, 20), exif=exif.tobytes()), "image/jpeg", str(tmp_path))
    with Image.open(tmp_path / nome) as img:
        assert img.size == (20, 60)


def test_pasta_inexistente_e_criada(tmp_path: Path) -> None:
    pasta = tmp_path / "a" / "b"
    tratar_e_salvar(imagem((10, 10)), "image/jpeg", str(pasta))
    assert len(list(pasta.iterdir())) == 1


def test_duas_fotos_iguais_ganham_nomes_diferentes(tmp_path: Path) -> None:
    a = tratar_e_salvar(imagem((10, 10)), "image/jpeg", str(tmp_path))
    b = tratar_e_salvar(imagem((10, 10)), "image/jpeg", str(tmp_path))
    assert a != b


# ---------- contexto hidrologico ----------


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def leituras(
    s: Session,
    codigo: str,
    variavel: str,
    pontos: list[tuple[datetime, float]],
    qualidade: str = "ok",
) -> None:
    est = s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()
    fonte = s.scalars(select(Fonte).where(Fonte.codigo == "dcsc_rest")).one()
    for t, v in pontos:
        s.add(
            Leitura(
                estacao_id=est.id,
                variavel=variavel,
                valor=v,
                unidade="x",
                medido_em=t,
                fonte_id=fonte.id,
                qualidade=qualidade,
            )
        )
    s.commit()


def test_sem_nenhum_dado_diz_indisponivel(base: Session) -> None:
    assert contexto_hidrologico(base, T0) == {"disponivel": False, "niveis": {}, "chuva_24h_mm": {}}


def test_nivel_mais_proximo_dentro_de_20_minutos_vence_o_mais_distante(base: Session) -> None:
    leituras(
        base,
        "DCSC-00043",
        "nivel_m",
        [(T0 - timedelta(minutes=15), 1.0), (T0 + timedelta(minutes=3), 2.456)],
    )
    ctx = contexto_hidrologico(base, T0)
    assert ctx["niveis"]["DCSC-00043"]["nivel_m"] == 2.46
    assert ctx["niveis"]["DCSC-00043"]["medido_em"] == (T0 + timedelta(minutes=3)).isoformat()


def test_nivel_alem_da_tolerancia_de_20_minutos_nao_serve(base: Session) -> None:
    assert timedelta(minutes=20) == TOLERANCIA_NIVEL
    leituras(
        base,
        "DCSC-00043",
        "nivel_m",
        [(T0 - timedelta(minutes=21), 1.0), (T0 + timedelta(minutes=21), 2.0)],
    )
    assert contexto_hidrologico(base, T0)["niveis"] == {}


def test_nivel_na_borda_exata_da_tolerancia_serve(base: Session) -> None:
    leituras(base, "DCSC-00043", "nivel_m", [(T0 - timedelta(minutes=20), 1.5)])
    assert contexto_hidrologico(base, T0)["niveis"]["DCSC-00043"]["nivel_m"] == 1.5


def test_leitura_suspeita_nao_entra_no_contexto(base: Session) -> None:
    leituras(base, "DCSC-00043", "nivel_m", [(T0, 9.9)], qualidade="suspeita")
    assert contexto_hidrologico(base, T0)["disponivel"] is False


def test_o_revolver_tambem_e_alvo_e_traz_o_proprio_nivel(base: Session) -> None:
    leituras(base, "DCSC-00174", "nivel_m", [(T0, 0.81)])
    leituras(base, "DCSC-00043", "nivel_m", [(T0, 3.5)])
    niveis = contexto_hidrologico(base, T0)["niveis"]
    assert niveis["DCSC-00174"]["nivel_m"] == 0.81 and niveis["DCSC-00043"]["nivel_m"] == 3.5


def test_estacao_de_influencia_nunca_entra_em_niveis(base: Session) -> None:
    leituras(base, "DCSC-00021", "nivel_m", [(T0, 3.0)])
    assert contexto_hidrologico(base, T0)["niveis"] == {}


def serie_chuva(
    inicio: datetime, n: int, passo_s: int = 300, valor: float = 0.1
) -> list[tuple[datetime, float]]:
    return [(inicio + timedelta(seconds=passo_s * i), valor) for i in range(n)]


def test_chuva_24h_exige_230_leituras_de_288(base: Session) -> None:
    assert MIN_LEITURAS_CHUVA_24H == 230
    ini = T0 - timedelta(hours=23, minutes=55)
    leituras(base, "DCSC-00043", "chuva_acumulada_mm", serie_chuva(ini, 229))
    assert contexto_hidrologico(base, T0)["chuva_24h_mm"] == {}
    leituras(
        base, "DCSC-00043", "chuva_acumulada_mm", [(ini + timedelta(seconds=300 * 229 + 1), 0.1)]
    )
    assert contexto_hidrologico(base, T0)["chuva_24h_mm"] == {"DCSC-00043": 23.0}


def test_janela_de_chuva_exclui_o_inicio_e_inclui_o_instante_do_registro(base: Session) -> None:
    leituras(
        base,
        "DCSC-00037",
        "chuva_acumulada_mm",
        [(T0 - timedelta(hours=24), 500.0), (T0, 0.1)]
        + serie_chuva(T0 - timedelta(hours=23, minutes=55), 288)[:-1],
    )
    # 500 mm exatamente 24 h antes fica fora; a leitura em T0 entra
    assert contexto_hidrologico(base, T0)["chuva_24h_mm"]["DCSC-00037"] == pytest.approx(
        28.8, abs=0.1
    )


def test_chuva_depois_do_momento_da_ocorrencia_nao_entra(base: Session) -> None:
    pontos = serie_chuva(T0 - timedelta(hours=23, minutes=55), 288) + [
        (T0 + timedelta(minutes=5), 400.0)
    ]
    leituras(base, "DCSC-00043", "chuva_acumulada_mm", pontos)
    assert contexto_hidrologico(base, T0)["chuva_24h_mm"]["DCSC-00043"] == pytest.approx(
        28.8, abs=0.1
    )


def test_contexto_so_com_chuva_ja_conta_como_disponivel(base: Session) -> None:
    leituras(
        base,
        "DCSC-00043",
        "chuva_acumulada_mm",
        serie_chuva(T0 - timedelta(hours=23, minutes=55), 288),
    )
    ctx = contexto_hidrologico(base, T0)
    assert ctx["disponivel"] is True and ctx["niveis"] == {}


# ---------- token ----------


def test_token_sem_assinatura_alg_none_e_recusado(client: TestClient, s: Session) -> None:
    semear(s)
    s.add(
        Usuario(
            nome="L",
            email="l@exemplo.br",
            papel="moderador",
            senha_hash=hash_senha("senha-forte-123"),
        )
    )
    s.commit()
    forjado = jwt.encode({"sub": "l@exemplo.br", "papel": "admin"}, None, algorithm="none")
    r = client.get(
        "/api/ocorrencias",
        params={"status": "pendente"},
        headers={"Authorization": f"Bearer {forjado}"},
    )
    assert r.status_code == 401


def test_token_assinado_com_outro_segredo_e_recusado(client: TestClient, s: Session) -> None:
    semear(s)
    s.add(
        Usuario(
            nome="L",
            email="l@exemplo.br",
            papel="moderador",
            senha_hash=hash_senha("senha-forte-123"),
        )
    )
    s.commit()
    assert obter_configuracao().jwt_secret != "outro-segredo-" * 3
    falso = jwt.encode(
        {"sub": "l@exemplo.br", "papel": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "outro-segredo-" * 3,
        algorithm="HS256",
    )
    r = client.get(
        "/api/ocorrencias",
        params={"status": "pendente"},
        headers={"Authorization": f"Bearer {falso}"},
    )
    assert r.status_code == 401
