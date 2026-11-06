"""Casos de borda da carga historica do painel municipal: janelas, estacoes e falhas."""

import zlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from common.enums import Variavel
from common.models import Estacao, Leitura
from common.seed import semear
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ingestor.adapters.pdc import Pdc
from ingestor.carga_pdc import DIAS_JANELA, INICIO_HISTORICO, carregar
from ingestor.erros import ContratoQuebrado

DESDE = date(2026, 11, 1)
ATE = datetime(2026, 11, 5, tzinfo=UTC)


def registro(id_: int, codigo: str, created_at: str, **campos: Any) -> dict[str, Any]:
    base = {
        "id": id_,
        "sta_code": codigo,
        "created_at": created_at,
        "river_level": None,
        "rainfall_1h": 0.5,
    }
    return {**base, **campos}


class Falso:
    """Servidor falso por estacao: devolve um registro por consulta, com id unico por chamada."""

    def __init__(self, falhar: set[str] | None = None, vazio: set[str] | None = None) -> None:
        self.consultas: list[dict[str, str]] = []
        self.falhar = falhar or set()
        self.vazio = vazio or set()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        params = dict(req.url.params)
        self.consultas.append(params)
        codigo = params["code"]
        if codigo in self.falhar:
            return httpx.Response(500)
        if codigo in self.vazio:
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        # 1 leitura no meio de cada janela consultada, com id estavel por (estacao, janela)
        ini = datetime.fromisoformat(params["from"])
        meio = (ini + timedelta(hours=1)).isoformat()
        id_ = zlib.crc32(f"{codigo}|{params['from']}".encode())
        return httpx.Response(
            200, json={"data": [registro(id_, codigo, meio)], "next_cursor": None}
        )


def pdc_com(falso: Falso) -> Pdc:
    cliente = httpx.Client(transport=httpx.MockTransport(falso))
    return Pdc("https://pdc.exemplo.test", "chave-ficticia", cliente=cliente, intervalo_min_s=0)


@pytest.fixture
def banco(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def test_constantes_do_historico() -> None:
    assert date(2025, 9, 13) == INICIO_HISTORICO
    assert DIAS_JANELA == 7


def test_janelas_sao_contiguas_comecam_em_desde_a_meia_noite_utc_e_terminam_em_ate(
    banco: Session,
) -> None:
    falso = Falso()
    carregar(pdc_com(falso), DESDE, ATE, estacoes=["DC-PEU-002"], dias_janela=3)
    de = [datetime.fromisoformat(c["from"]) for c in falso.consultas]
    ate = [datetime.fromisoformat(c["to"]) for c in falso.consultas]
    assert de[0] == datetime(2026, 11, 1, tzinfo=UTC)
    assert ate[-1] == ATE
    assert de[1:] == ate[:-1]  # sem buraco nem sobreposicao
    assert [b - a for a, b in zip(de, ate, strict=True)] == [timedelta(days=3), timedelta(days=1)]


def test_ate_antes_de_desde_nao_consulta_nada_e_zera_os_totais(banco: Session) -> None:
    falso = Falso()
    totais = carregar(
        pdc_com(falso), date(2026, 11, 10), datetime(2026, 11, 5, tzinfo=UTC), ["DC-PEU-002"]
    )
    assert falso.consultas == [] and totais == {"DC-PEU-002": 0}


@pytest.mark.parametrize("dias", [0, -1, 32, 100])
def test_tamanho_de_janela_fora_de_1_a_31_e_recusado_sem_consultar(dias: int) -> None:
    falso = Falso()
    with pytest.raises(ValueError, match="dias_janela"):
        carregar(pdc_com(falso), DESDE, ATE, dias_janela=dias)
    assert falso.consultas == []


@pytest.mark.parametrize("dias", [1, 31])
def test_tamanhos_de_janela_nos_limites_sao_aceitos(banco: Session, dias: int) -> None:
    falso = Falso()
    carregar(pdc_com(falso), DESDE, ATE, estacoes=["DC-PEU-002"], dias_janela=dias)
    assert len(falso.consultas) == -(-4 // dias)  # ceil(4 dias / janela)


def test_estacao_sem_mapeamento_e_recusada_antes_de_consultar() -> None:
    falso = Falso()
    with pytest.raises(KeyError):
        carregar(pdc_com(falso), DESDE, ATE, estacoes=["DCSC-00021"])
    assert falso.consultas == []


def test_sem_lista_de_estacoes_carrega_as_sete_do_painel_com_a_creche_na_00174(
    banco: Session,
) -> None:
    falso = Falso()
    totais = carregar(pdc_com(falso), DESDE, ATE, dias_janela=7)
    assert set(totais) == {
        "DCSC-00174",
        "DC-PEU-002",
        "DC-PEU-003",
        "DC-PEU-004",
        "DCSC-00037",
        "DCSC-00043",
        "DCSC-00015",
    }
    assert {c["code"] for c in falso.consultas} == {
        "DC-PEU-001",
        "DC-PEU-002",
        "DC-PEU-003",
        "DC-PEU-004",
        "DCSC-00037",
        "DCSC-00043",
        "DCSC-00015",
    }
    assert all(n == 1 for n in totais.values())  # uma janela por estacao, uma leitura em cada


def test_codigo_do_painel_e_do_banco_da_creche_somam_na_mesma_chave(banco: Session) -> None:
    falso = Falso()
    totais = carregar(pdc_com(falso), DESDE, ATE, estacoes=["DC-PEU-001", "DCSC-00174"])
    # a mesma estacao pedida duas vezes: a 2a passada nao traz nada novo
    assert totais == {"DCSC-00174": 1}


def test_estacoes_novas_gravam_so_chuva_na_estacao_certa(banco: Session) -> None:
    carregar(pdc_com(Falso()), DESDE, ATE, estacoes=["DC-PEU-003", "DC-PEU-004"], dias_janela=31)
    linhas = banco.execute(
        select(Estacao.codigo, Leitura.variavel, func.count())
        .join(Leitura, Leitura.estacao_id == Estacao.id)
        .group_by(Estacao.codigo, Leitura.variavel)
    ).all()
    assert sorted(linhas) == [
        ("DC-PEU-003", Variavel.CHUVA_H001_MM.value, 1),
        ("DC-PEU-004", Variavel.CHUVA_H001_MM.value, 1),
    ]


def test_estacao_vazia_na_fonte_nao_atrapalha_as_outras(banco: Session) -> None:
    falso = Falso(vazio={"DC-PEU-002"})
    totais = carregar(pdc_com(falso), DESDE, ATE, estacoes=["DC-PEU-002", "DC-PEU-003"])
    assert totais["DC-PEU-002"] == 0 and totais["DC-PEU-003"] > 0


def test_estacao_inteira_fora_do_ar_nao_derruba_as_demais_nem_levanta(banco: Session) -> None:
    falso = Falso(falhar={"DC-PEU-002"})
    totais = carregar(
        pdc_com(falso), DESDE, ATE, estacoes=["DC-PEU-002", "DC-PEU-003"], dias_janela=2
    )
    assert totais["DC-PEU-002"] == 0 and totais["DC-PEU-003"] == 2
    # todas as janelas da estacao quebrada foram tentadas, nenhuma foi pulada
    assert sum(c["code"] == "DC-PEU-002" for c in falso.consultas) == 2


def test_todas_as_janelas_de_todas_as_estacoes_falhando_termina_com_totais_zero(
    banco: Session,
) -> None:
    falso = Falso(falhar={"DC-PEU-002", "DC-PEU-003"})
    totais = carregar(pdc_com(falso), DESDE, ATE, estacoes=["DC-PEU-002", "DC-PEU-003"])
    assert totais == {"DC-PEU-002": 0, "DC-PEU-003": 0}
    assert banco.scalar(select(func.count()).select_from(Leitura)) == 0


def test_contrato_quebrado_interrompe_a_carga_em_vez_de_gravar_lixo(banco: Session) -> None:
    def quebrado(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"formato": "novo"}], "next_cursor": None})

    cliente = httpx.Client(transport=httpx.MockTransport(quebrado))
    pdc = Pdc("https://pdc.exemplo.test", "chave-ficticia", cliente=cliente, intervalo_min_s=0)
    with pytest.raises(ContratoQuebrado):
        carregar(pdc, DESDE, ATE, estacoes=["DC-PEU-002"])
    assert banco.scalar(select(func.count()).select_from(Leitura)) == 0


def test_banco_sem_seed_falha_alto_em_vez_de_perder_o_historico_em_silencio(s: Session) -> None:
    with pytest.raises(LookupError, match="rode o seed"):
        carregar(pdc_com(Falso()), DESDE, ATE, estacoes=["DC-PEU-002"])


def test_estacao_removida_do_banco_nao_grava_nada_e_total_fica_zero(banco: Session) -> None:
    banco.delete(banco.scalars(select(Estacao).where(Estacao.codigo == "DC-PEU-002")).one())
    banco.commit()
    totais = carregar(pdc_com(Falso()), DESDE, ATE, estacoes=["DC-PEU-002"])
    assert totais == {"DC-PEU-002": 0}
    assert banco.scalar(select(func.count()).select_from(Leitura)) == 0


def test_leitura_de_nivel_do_painel_cai_na_00174_com_a_fonte_do_painel(banco: Session) -> None:
    def com_nivel(req: httpx.Request) -> httpx.Response:
        r = registro(1, "DC-PEU-001", "2026-11-02T10:00:00+00:00", river_level=0.8)
        return httpx.Response(200, json={"data": [r], "next_cursor": None})

    cliente = httpx.Client(transport=httpx.MockTransport(com_nivel))
    pdc = Pdc("https://pdc.exemplo.test", "chave-ficticia", cliente=cliente, intervalo_min_s=0)
    totais = carregar(pdc, DESDE, ATE, estacoes=["DC-PEU-001"], dias_janela=31)
    assert totais == {"DCSC-00174": 2}  # nivel + chuva h001
    nivel = banco.scalars(select(Leitura).where(Leitura.variavel == "nivel_m")).one()
    assert nivel.valor == 0.8 and nivel.medido_em == datetime(2026, 11, 2, 10, tzinfo=UTC)
