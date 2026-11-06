"""Falhas que nao podem ser engolidas: carga historica do painel e coleta da REST."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from common.config import obter_configuracao

from ingestor import carga_pdc
from ingestor.adapters.dcsc_rest import DcscRest
from ingestor.adapters.pdc import Pdc
from ingestor.carga_pdc import carregar, principal
from ingestor.erros import ChaveRecusada, FonteIndisponivel

T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def pdc_status(status: int, vistas: list[httpx.Request]) -> Pdc:
    def responder(req: httpx.Request) -> httpx.Response:
        vistas.append(req)
        return httpx.Response(status)

    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    return Pdc("https://pdc.exemplo.test", "chave-ficticia", cliente=cliente, intervalo_min_s=0)


@pytest.mark.parametrize("status", [401, 403])
def test_chave_recusada_aborta_a_carga_na_primeira_chamada(status: int) -> None:
    vistas: list[httpx.Request] = []
    with pytest.raises(ChaveRecusada):
        carregar(pdc_status(status, vistas), desde=T0.date(), ate=T0 + timedelta(days=30))
    assert len(vistas) == 1  # nao segue fazendo centenas de chamadas


def test_chave_recusada_continua_sendo_fonte_indisponivel() -> None:
    assert issubclass(ChaveRecusada, FonteIndisponivel)


def test_janela_com_falha_e_anotada_para_o_chamador() -> None:
    falhas: list[str] = []
    carregar(
        pdc_status(500, []),
        desde=T0.date() - timedelta(days=3),
        ate=T0,
        estacoes=["DC-PEU-002"],
        dias_janela=2,
        falhas=falhas,
    )
    assert len(falhas) == 2 and all(f.startswith("DC-PEU-002 ") for f in falhas)


def _linha_de_comando(monkeypatch: pytest.MonkeyPatch, pdc: Pdc) -> None:
    monkeypatch.setenv("PDC_API_KEY", "chave-ficticia")
    obter_configuracao.cache_clear()
    monkeypatch.setattr(carga_pdc, "Pdc", lambda *a, **k: pdc)


def test_saida_e_diferente_de_zero_quando_alguma_janela_falha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _linha_de_comando(monkeypatch, pdc_status(500, []))
    assert principal(["--estacao", "DC-PEU-002", "--desde", "2026-11-03"]) == 1
    obter_configuracao.cache_clear()


def test_saida_e_diferente_de_zero_quando_a_chave_e_recusada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _linha_de_comando(monkeypatch, pdc_status(401, []))
    assert principal(["--estacao", "DC-PEU-002", "--desde", "2026-11-03"]) == 3
    obter_configuracao.cache_clear()


def test_saida_e_diferente_de_zero_sem_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDC_API_KEY", "")
    obter_configuracao.cache_clear()
    assert principal([]) == 2
    obter_configuracao.cache_clear()


def _rest(resposta: Any, estacoes: list[str]) -> DcscRest:
    cliente = httpx.Client(transport=httpx.MockTransport(resposta))
    return DcscRest("https://x.test", estacoes, cliente)


def test_rest_todas_as_estacoes_fora_do_ar_levanta_fonte_indisponivel() -> None:
    rest = _rest(lambda req: httpx.Response(503), ["DCSC-00043", "DCSC-00021"])
    with pytest.raises(FonteIndisponivel, match="nenhuma estacao respondeu"):
        rest.coletar(T0 - timedelta(hours=2), T0)


def test_rest_estacao_que_responde_vazia_nao_e_falha() -> None:
    rest = _rest(lambda req: httpx.Response(200, json={"dados": []}), ["DCSC-00043"])
    assert rest.coletar(T0 - timedelta(hours=2), T0) == []
