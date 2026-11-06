"""Casos de borda do adaptador do painel municipal (PDC): fuso, taxa, paginacao e erros.

Complementa test_pdc.py (contrato com resposta gravada, caminho feliz e erros principais).
"""

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from common.enums import Variavel
from common.seed import ESTACOES, ESTACOES_PDC, FONTES

from ingestor.adapters import pdc as modulo_pdc
from ingestor.adapters.pdc import (
    CODIGOS,
    ESPERA_429_MAX_S,
    Pdc,
    codigo_pdc,
    janelas,
    normalizar,
)
from ingestor.erros import ContratoQuebrado, FonteIndisponivel

CHAVE = "chave-ficticia-de-teste"
BASE = "https://pdc.exemplo.test/stations-api"
INI = datetime(2026, 11, 4, 19, 0, tzinfo=UTC)
FIM = INI + timedelta(hours=1)


def reg(id_: int | None, minuto: int = 0, **campos: Any) -> dict[str, Any]:
    """Registro minimo da API do painel; `minuto` desloca o created_at (UTC)."""
    base: dict[str, Any] = {
        "sta_code": "DC-PEU-002",
        "created_at": (INI + timedelta(minutes=minuto)).isoformat(),
        "river_level": None,
        "rainfall_1h": 1.0,
    }
    if id_ is not None:
        base["id"] = id_
    return {**base, **campos}


class Roteiro:
    """Cliente httpx falso: respostas em ordem (a ultima se repete) e requisicoes guardadas."""

    def __init__(self, respostas: list[Any]) -> None:
        self.respostas = respostas
        self.requisicoes: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requisicoes.append(req)
        r = self.respostas[min(len(self.requisicoes), len(self.respostas)) - 1]
        if isinstance(r, Exception):
            raise r
        return r


def ok(data: list[dict[str, Any]], proximo: str | None = None) -> httpx.Response:
    return httpx.Response(200, json={"data": data, "next_cursor": proximo})


def montar(roteiro: Roteiro, **kw: Any) -> tuple[Pdc, list[float]]:
    dormidas: list[float] = []
    cliente = httpx.Client(transport=httpx.MockTransport(roteiro))
    kw.setdefault("intervalo_min_s", 0.0)
    kw.setdefault("base_url", BASE)
    base_url = kw.pop("base_url")
    return Pdc(base_url, CHAVE, cliente=cliente, dormir=dormidas.append, **kw), dormidas


# --- mapeamento de codigos --------------------------------------------------------------


def test_codigo_pdc_aceita_o_codigo_do_painel_e_o_do_nosso_banco() -> None:
    assert codigo_pdc("DC-PEU-001") == "DC-PEU-001"
    assert codigo_pdc("DCSC-00174") == "DC-PEU-001"
    assert codigo_pdc("DC-PEU-003") == "DC-PEU-003"


def test_codigo_pdc_desconhecido_levanta_keyerror() -> None:
    with pytest.raises(KeyError, match="DCSC-00021"):
        codigo_pdc("DCSC-00021")  # estacao estadual que nao esta no painel municipal


def test_construtor_recusa_estacao_sem_mapeamento() -> None:
    with pytest.raises(KeyError):
        Pdc(BASE, CHAVE, estacoes=["DC-PEU-001", "XYZ"])


def test_toda_estacao_de_destino_do_adaptador_existe_no_seed() -> None:
    """Se faltar no seed, `gravar` descarta a leitura em silencio (estacao nao configurada)."""
    codigos_seed = {e[0] for e in ESTACOES} | {e[0] for e in ESTACOES_PDC}
    assert set(CODIGOS.values()) <= codigos_seed


def test_a_fonte_do_adaptador_esta_no_seed_com_a_mesma_frequencia() -> None:
    fontes = {codigo: freq for codigo, _nome, _url, freq in FONTES}
    assert fontes[Pdc.codigo] == Pdc.frequencia_s == 300


def test_url_da_fonte_no_seed_nao_carrega_credencial() -> None:
    url = next(u for c, _n, u, _f in FONTES if c == "pdc_municipal").lower()
    assert "key" not in url and "token" not in url and "@" not in url


# --- janelas ----------------------------------------------------------------------------


def test_janelas_de_periodo_exato_em_multiplos_do_tamanho() -> None:
    ini = datetime(2025, 9, 13, tzinfo=UTC)
    lista = list(janelas(ini, ini + timedelta(days=62)))
    assert len(lista) == 2 and lista[0][1] - lista[0][0] == timedelta(days=31)
    assert lista[-1][1] == ini + timedelta(days=62)


def test_janelas_periodo_curto_gera_uma_so_com_os_limites_dados() -> None:
    assert list(janelas(INI, FIM)) == [(INI, FIM)]


def test_janelas_com_inicio_igual_ao_fim_nao_gera_consulta() -> None:
    assert list(janelas(INI, INI)) == []


def test_janelas_um_segundo_alem_do_tamanho_gera_janela_final_minima() -> None:
    lista = list(janelas(INI, INI + timedelta(days=31, seconds=1)))
    assert [b - a for a, b in lista] == [timedelta(days=31), timedelta(seconds=1)]


# --- fuso e formato dos parametros ------------------------------------------------------


def test_datas_da_consulta_saem_em_utc_mesmo_com_fuso_local() -> None:
    brasilia = timezone(timedelta(hours=-3))
    roteiro = Roteiro([ok([])])
    pdc, _ = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI.astimezone(brasilia), FIM.astimezone(brasilia))
    params = roteiro.requisicoes[0].url.params
    assert (params["from"], params["to"]) == ("2026-11-04T19:00:00Z", "2026-11-04T20:00:00Z")


def test_datetime_sem_fuso_e_recusado_para_nao_deslocar_a_consulta() -> None:
    roteiro = Roteiro([ok([])])
    pdc, _ = montar(roteiro)
    ingenuo_ini = datetime(2026, 11, 4, 19)  # noqa: DTZ001
    ingenuo_fim = datetime(2026, 11, 4, 20)  # noqa: DTZ001
    with pytest.raises(ValueError, match="fuso"):
        pdc.coletar_estacao("DC-PEU-002", ingenuo_ini, ingenuo_fim)
    assert roteiro.requisicoes == []
    with pytest.raises(TypeError):  # um com fuso e outro sem: nem chega a comparar
        pdc.coletar_estacao("DC-PEU-002", ingenuo_ini, FIM)
    assert roteiro.requisicoes == []


def test_barra_final_na_url_base_nao_duplica_a_barra() -> None:
    roteiro = Roteiro([ok([])])
    pdc, _ = montar(roteiro, base_url=BASE + "/")
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert roteiro.requisicoes[0].url.path == "/stations-api/readings"


def test_a_chave_vai_no_cabecalho_de_todas_as_paginas_e_nunca_na_url() -> None:
    roteiro = Roteiro([ok([reg(1)], "c1"), ok([reg(1), reg(2, 5)], None)])
    pdc, _ = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=2)
    assert len(roteiro.requisicoes) == 2
    for req in roteiro.requisicoes:
        assert req.headers["x-api-key"] == CHAVE
        assert CHAVE not in str(req.url)


# --- normalizar: tipos e fuso -----------------------------------------------------------


def test_created_at_com_outro_fuso_e_convertido_para_utc() -> None:
    r = reg(1, created_at="2026-11-04T16:07:18-03:00", rainfall_1h=2.0)
    leitura = normalizar({"data": [r]})[0]
    assert leitura.medido_em == datetime(2026, 11, 4, 19, 7, 18, tzinfo=UTC)
    assert leitura.medido_em.utcoffset() == timedelta(0)


def test_valor_inteiro_vira_float_e_zero_e_leitura_valida() -> None:
    leitura = normalizar({"data": [reg(1, rainfall_1h=0)]})[0]
    assert leitura.valor == 0.0 and isinstance(leitura.valor, float)


def test_valor_booleano_ou_texto_nao_vira_leitura() -> None:
    for invalido in (True, False, "0.4", [1], {"v": 1}):
        assert normalizar({"data": [reg(1, rainfall_1h=invalido)]}) == []


def test_registro_com_nivel_e_chuva_gera_duas_leituras_no_mesmo_instante() -> None:
    leituras = normalizar({"data": [reg(1, sta_code="DC-PEU-001", river_level=1.2)]})
    assert {x.variavel for x in leituras} == {Variavel.NIVEL_M, Variavel.CHUVA_H001_MM}
    assert len({x.medido_em for x in leituras}) == 1
    assert {x.estacao_codigo for x in leituras} == {"DCSC-00174"}


def test_registro_com_todos_os_campos_nulos_e_valido_mas_sem_leituras() -> None:
    assert normalizar({"data": [reg(1, river_level=None, rainfall_1h=None)]}) == []


def test_pagina_vazia_nao_e_erro() -> None:
    assert normalizar({"data": []}) == []


@pytest.mark.parametrize("resposta", [[], "texto", None, 3])
def test_resposta_que_nao_e_objeto_levanta_contrato_quebrado(resposta: Any) -> None:
    with pytest.raises(ContratoQuebrado):
        normalizar(resposta)


@pytest.mark.parametrize("codigo", [None, "", 7])
def test_sta_code_ausente_vazio_ou_nao_texto_e_contrato_quebrado(codigo: Any) -> None:
    with pytest.raises(ContratoQuebrado, match="sta_code"):
        normalizar({"data": [reg(1, sta_code=codigo)]})


def test_created_at_nulo_ou_nao_texto_e_contrato_quebrado() -> None:
    for invalido in (None, 123):
        with pytest.raises(ContratoQuebrado, match="created_at"):
            normalizar({"data": [reg(1, created_at=invalido)]})


def test_o_bruto_nao_carrega_a_chave_da_api() -> None:
    leitura = normalizar({"data": [reg(1)]})[0]
    assert CHAVE not in str(leitura.bruto)


# --- paginacao --------------------------------------------------------------------------


def test_mesmo_id_nas_duas_janelas_conta_uma_vez() -> None:
    """Linha na fronteira de duas janelas de 31 dias aparece nas duas respostas."""
    ini = datetime(2025, 9, 13, tzinfo=UTC)
    na_fronteira = reg(7, rainfall_1h=3.0)
    roteiro = Roteiro([ok([reg(6), na_fronteira]), ok([na_fronteira, reg(8, 5)])])
    pdc, _ = montar(roteiro)
    leituras = pdc.coletar_estacao("DC-PEU-002", ini, ini + timedelta(days=40))
    assert len(roteiro.requisicoes) == 2
    assert len(leituras) == 3  # ids 6, 7 e 8; o 7 nao dobra


def test_registros_sem_id_nao_sao_descartados_como_repetidos() -> None:
    roteiro = Roteiro([ok([reg(None, 0), reg(None, 5)])])
    pdc, _ = montar(roteiro)
    assert len(pdc.coletar_estacao("DC-PEU-002", INI, FIM)) == 2


def test_pagina_sem_linha_nova_encerra_mesmo_com_cursor_diferente() -> None:
    roteiro = Roteiro([ok([reg(1), reg(2, 5)], "c1"), ok([reg(2, 5)], "c2"), ok([reg(9, 50)])])
    pdc, _ = montar(roteiro)
    leituras = pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=2)
    assert len(roteiro.requisicoes) == 2 and len(leituras) == 2


def test_cursor_igual_ao_anterior_encerra() -> None:
    roteiro = Roteiro([ok([reg(1)], "c1"), ok([reg(2, 5)], "c1"), ok([reg(3, 10)], "c2")])
    pdc, _ = montar(roteiro)
    leituras = pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=2)
    assert len(roteiro.requisicoes) == 2 and len(leituras) == 2


def test_cursor_da_pagina_anterior_e_enviado_na_seguinte_e_nao_na_primeira() -> None:
    roteiro = Roteiro([ok([reg(1)], "c1"), ok([reg(1), reg(2, 5)], None)])
    pdc, _ = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=2)
    assert "cursor" not in roteiro.requisicoes[0].url.params
    assert roteiro.requisicoes[1].url.params["cursor"] == "c1"


@pytest.mark.parametrize("limite", [0, 1, 1001, -5])
def test_limite_fora_de_2_a_1000_e_recusado_antes_de_qualquer_chamada(limite: int) -> None:
    roteiro = Roteiro([ok([])])
    pdc, _ = montar(roteiro)
    with pytest.raises(ValueError, match="limite"):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=limite)
    assert roteiro.requisicoes == []


@pytest.mark.parametrize("limite", [2, 1000])
def test_limites_extremos_validos_sao_enviados_como_pedidos(limite: int) -> None:
    roteiro = Roteiro([ok([])])
    pdc, _ = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=limite)
    assert roteiro.requisicoes[0].url.params["limit"] == str(limite)


def test_estacao_desconhecida_na_api_devolve_lista_vazia_sem_erro() -> None:
    """Codigo que a fonte nao conhece volta 200 com lista vazia (docs, secao 8.1)."""
    pdc, _ = montar(Roteiro([ok([])]))
    assert pdc.coletar_estacao("DC-PEU-004", INI, FIM) == []


def test_todas_as_estacoes_respondem_vazio_e_coleta_vazia_nao_e_falha() -> None:
    pdc, _ = montar(Roteiro([ok([])]))
    assert pdc.coletar(INI, FIM) == []


def test_erro_na_segunda_pagina_descarta_a_estacao_inteira_em_vez_de_devolver_parcial() -> None:
    roteiro = Roteiro([ok([reg(1)], "c1"), httpx.Response(500)])
    pdc, _ = montar(roteiro)
    with pytest.raises(FonteIndisponivel, match="500"):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=2)


def test_contrato_quebrado_em_uma_estacao_interrompe_a_coleta_toda() -> None:
    """Formato novo e problema da fonte inteira: sobe para `executar` registrar a falha."""
    roteiro = Roteiro([ok([{"sem": "campos"}])])
    pdc, _ = montar(roteiro, estacoes=["DC-PEU-001", "DC-PEU-002"])
    with pytest.raises(ContratoQuebrado):
        pdc.coletar(INI, FIM)
    assert len(roteiro.requisicoes) == 1


# --- erros HTTP e taxa ------------------------------------------------------------------


def test_404_vira_fonte_indisponivel_com_o_status() -> None:
    pdc, _ = montar(Roteiro([httpx.Response(404)]))
    with pytest.raises(FonteIndisponivel, match="404"):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM)


@pytest.mark.parametrize("status", [401, 403])
def test_chave_recusada_nao_tenta_de_novo(status: int) -> None:
    roteiro = Roteiro([httpx.Response(status)])
    pdc, dormidas = montar(roteiro)
    with pytest.raises(FonteIndisponivel, match="chave recusada"):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert len(roteiro.requisicoes) == 1 and dormidas == []


def test_5xx_nao_e_repetido_pelo_adaptador() -> None:
    roteiro = Roteiro([httpx.Response(503)])
    pdc, dormidas = montar(roteiro)
    with pytest.raises(FonteIndisponivel):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert len(roteiro.requisicoes) == 1 and dormidas == []


def test_timeout_vira_fonte_indisponivel() -> None:
    pdc, _ = montar(Roteiro([httpx.ReadTimeout("lento")]))
    with pytest.raises(FonteIndisponivel, match="ReadTimeout"):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM)


def test_retry_after_acima_do_teto_espera_no_maximo_o_teto() -> None:
    roteiro = Roteiro([httpx.Response(429, headers={"retry-after": "3600"}), ok([])])
    pdc, dormidas = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert dormidas == [ESPERA_429_MAX_S]


def test_retry_after_negativo_nao_gera_espera_negativa() -> None:
    roteiro = Roteiro([httpx.Response(429, headers={"retry-after": "-5"}), ok([])])
    pdc, dormidas = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert dormidas == [0.0]


def test_retry_after_em_formato_de_data_cai_no_recuo_progressivo() -> None:
    data_http = "Wed, 21 Oct 2026 07:28:00 GMT"
    roteiro = Roteiro(
        [
            httpx.Response(429, headers={"retry-after": data_http}),
            httpx.Response(429, headers={"retry-after": data_http}),
            httpx.Response(429),
            ok([]),
        ]
    )
    pdc, dormidas = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert dormidas == [5.0, 10.0, 20.0]


def test_recuo_progressivo_sem_retry_after_dobra_a_cada_tentativa() -> None:
    roteiro = Roteiro([httpx.Response(429)] * 3 + [ok([])])
    pdc, dormidas = montar(roteiro)
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert dormidas == [5.0, 10.0, 20.0]
    assert modulo_pdc.TENTATIVAS_429 == 3


def test_429_no_meio_da_paginacao_retoma_a_mesma_pagina_com_o_mesmo_cursor() -> None:
    roteiro = Roteiro(
        [ok([reg(1)], "c1"), httpx.Response(429, headers={"retry-after": "1"}), ok([reg(2, 5)])]
    )
    pdc, dormidas = montar(roteiro)
    leituras = pdc.coletar_estacao("DC-PEU-002", INI, FIM, limite=2)
    assert len(leituras) == 2 and dormidas == [1.0]
    assert [r.url.params.get("cursor") for r in roteiro.requisicoes] == [None, "c1", "c1"]


def test_aviso_de_429_nao_vaza_a_chave(caplog: pytest.LogCaptureFixture) -> None:
    roteiro = Roteiro([httpx.Response(429, headers={"retry-after": "1"}), ok([])])
    pdc, _ = montar(roteiro)
    with caplog.at_level(logging.DEBUG, logger="ingestor.pdc"):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert any("limite de taxa" in r.getMessage() for r in caplog.records)
    assert CHAVE not in caplog.text


def test_falha_de_estacao_e_registrada_sem_a_chave(caplog: pytest.LogCaptureFixture) -> None:
    roteiro = Roteiro([httpx.Response(500)])
    pdc, _ = montar(roteiro, estacoes=["DC-PEU-001", "DC-PEU-002"])
    with caplog.at_level(logging.WARNING, logger="ingestor.pdc"), pytest.raises(FonteIndisponivel):
        pdc.coletar(INI, FIM)
    assert caplog.text.count("estacao do painel indisponivel") == 2
    assert CHAVE not in caplog.text


def test_mensagem_de_todas_falhando_informa_quantas_estacoes() -> None:
    pdc, _ = montar(Roteiro([httpx.Response(500)]), estacoes=["DC-PEU-001", "DC-PEU-002"])
    with pytest.raises(FonteIndisponivel, match=r"nenhuma estacao respondeu \(2\)"):
        pdc.coletar(INI, FIM)


def test_so_uma_estacao_configurada_e_ela_falha_tambem_levanta() -> None:
    pdc, _ = montar(Roteiro([httpx.Response(500)]), estacoes=["DC-PEU-003"])
    with pytest.raises(FonteIndisponivel, match="nenhuma estacao"):
        pdc.coletar(INI, FIM)


# --- ritmo das chamadas -----------------------------------------------------------------


def test_espera_so_o_que_falta_para_completar_o_intervalo_minimo() -> None:
    hora = [100.0]
    dormidas: list[float] = []
    roteiro = Roteiro([ok([])])
    cliente = httpx.Client(transport=httpx.MockTransport(roteiro))
    pdc = Pdc(
        BASE,
        CHAVE,
        cliente=cliente,
        dormir=dormidas.append,
        relogio=lambda: hora[0],
        intervalo_min_s=0.6,
    )
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)  # 1a chamada: sem espera
    hora[0] = 100.2
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)  # passaram 0,2 s: faltam 0,4 s
    hora[0] = 105.0
    pdc.coletar_estacao("DC-PEU-002", INI, FIM)  # passou muito mais que o minimo: sem espera
    assert dormidas == [pytest.approx(0.4)]


def test_intervalo_zero_nunca_dorme() -> None:
    roteiro = Roteiro([ok([])])
    pdc, dormidas = montar(roteiro)
    for _ in range(3):
        pdc.coletar_estacao("DC-PEU-002", INI, FIM)
    assert dormidas == []


# --- canario ----------------------------------------------------------------------------


def test_canario_falha_quando_nao_ha_nenhuma_leitura_aproveitavel() -> None:
    nulos = ok([reg(1, river_level=None, rainfall_1h=None)])
    pdc, _ = montar(Roteiro([nulos]))
    assert pdc.verificar_contrato() is False
    pdc, _ = montar(Roteiro([ok([])]))
    assert pdc.verificar_contrato() is False


def test_canario_falha_com_chave_recusada_e_com_rede_fora() -> None:
    for resposta in (httpx.Response(401), httpx.ConnectError("sem rede")):
        pdc, _ = montar(Roteiro([resposta]))
        assert pdc.verificar_contrato() is False


def test_canario_consulta_latest_com_a_chave() -> None:
    roteiro = Roteiro([ok([reg(1)])])
    pdc, _ = montar(roteiro)
    assert pdc.verificar_contrato() is True
    assert roteiro.requisicoes[0].url.path.endswith("/latest")
    assert roteiro.requisicoes[0].headers["x-api-key"] == CHAVE
