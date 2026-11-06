"""Adaptadores estaduais e Open-Meteo: erros de rede, formato quebrado e valores de borda."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from common.enums import Variavel

from ingestor.adapters.dcsc_barragens import ESTACAO_BARRAGEM_NORTE, DcscBarragens
from ingestor.adapters.dcsc_barragens import normalizar as norm_barragem
from ingestor.adapters.dcsc_graphql import QUERY_TAGS_DATA, DcscGraphql
from ingestor.adapters.dcsc_graphql import normalizar as norm_graphql
from ingestor.adapters.dcsc_rest import DcscRest
from ingestor.adapters.dcsc_rest import normalizar as norm_rest
from ingestor.adapters.openmeteo import (
    MODELO_FORECAST,
    OpenMeteo,
    normalizar_archive,
    normalizar_forecast,
)
from ingestor.erros import ContratoQuebrado, FonteIndisponivel

FIX = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def cliente(resposta: Any) -> tuple[httpx.Client, list[httpx.Request]]:
    vistas: list[httpx.Request] = []

    def tratar(req: httpx.Request) -> httpx.Response:
        vistas.append(req)
        r = resposta(req) if callable(resposta) else resposta
        if isinstance(r, Exception):
            raise r
        return r

    return httpx.Client(transport=httpx.MockTransport(tratar)), vistas


def graphql(estacoes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": {"tags_data": {"qualle_meteorologia": estacoes}}}


def est_graphql(codigo: str = "DCSC-00043", **dados: Any) -> dict[str, Any]:
    return {"codigo": codigo, "timestamp": "2026-11-05T12:00:00.000+00:00", "data": dados}


# ---------- GraphQL: normalizar ----------


def test_graphql_zero_e_valor_valido_e_texto_nao() -> None:
    est = est_graphql(
        rio={"rio_nivel": {"value": "1.2"}},
        chuva={"acumulado": {"h001": {"value": 0}, "h003": {"value": "2"}}},
    )
    leituras = norm_graphql(graphql([est]))
    assert [(x.variavel, x.valor) for x in leituras] == [(Variavel.CHUVA_H001_MM, 0.0)]


def test_graphql_estacao_com_data_nula_ou_sem_rio_nao_quebra() -> None:
    sem_data = {"codigo": "DCSC-00043", "timestamp": "2026-11-05T12:00:00+00:00", "data": None}
    sem_rio = est_graphql(chuva={"acumulado": {"h024": {"value": 3.5}}})
    leituras = norm_graphql(graphql([sem_data, sem_rio]))
    assert [(x.variavel, x.valor) for x in leituras] == [(Variavel.CHUVA_H024_MM, 3.5)]


def test_graphql_estacao_sem_codigo_ou_sem_horario_e_ignorada() -> None:
    sem_codigo = {**est_graphql(rio={"rio_nivel": {"value": 1.0}}), "codigo": None}
    sem_hora = {**est_graphql(rio={"rio_nivel": {"value": 1.0}}), "timestamp": ""}
    assert norm_graphql(graphql([sem_codigo, sem_hora])) == []


def test_graphql_lista_vazia_de_estacoes_nao_e_erro() -> None:
    assert norm_graphql(graphql([])) == []


def test_graphql_horario_com_z_e_convertido_para_utc() -> None:
    est = est_graphql(rio={"rio_nivel": {"value": 1.0}})
    est["timestamp"] = "2026-11-05T09:00:00-03:00"
    assert norm_graphql(graphql([est]))[0].medido_em == T0


def test_graphql_cada_janela_vira_a_variavel_certa() -> None:
    acumulado = {f"h{n:03d}": {"value": float(n)} for n in (1, 3, 6, 12, 24, 48, 72, 168)}
    leituras = norm_graphql(graphql([est_graphql(chuva={"acumulado": acumulado})]))
    assert {x.variavel: x.valor for x in leituras} == {
        Variavel.CHUVA_H001_MM: 1.0,
        Variavel.CHUVA_H003_MM: 3.0,
        Variavel.CHUVA_H006_MM: 6.0,
        Variavel.CHUVA_H012_MM: 12.0,
        Variavel.CHUVA_H024_MM: 24.0,
        Variavel.CHUVA_H048_MM: 48.0,
        Variavel.CHUVA_H072_MM: 72.0,
        Variavel.CHUVA_H168_MM: 168.0,
    }


def test_graphql_horario_invalido_e_contrato_quebrado() -> None:
    est = est_graphql(rio={"rio_nivel": {"value": 1.0}})
    est["timestamp"] = "ontem"
    with pytest.raises(ContratoQuebrado):
        norm_graphql(graphql([est]))


# ---------- GraphQL: rede ----------


def test_graphql_envia_a_operacao_registrada_exatamente_como_o_portal() -> None:
    c, vistas = cliente(httpx.Response(200, json=graphql([])))
    DcscGraphql("https://x.test/graphql", c).coletar()
    corpo = json.loads(vistas[0].content)
    assert corpo["operationName"] == "Tags_data" and corpo["query"] == QUERY_TAGS_DATA


@pytest.mark.parametrize("resposta", [httpx.Response(500), httpx.Response(200, text="<html>")])
def test_graphql_erro_http_ou_json_invalido_vira_fonte_indisponivel(
    resposta: httpx.Response,
) -> None:
    c, _ = cliente(resposta)
    with pytest.raises(FonteIndisponivel):
        DcscGraphql("https://x.test/graphql", c).coletar()


def test_graphql_erros_no_corpo_viram_contrato_quebrado_com_mensagem_curta() -> None:
    c, _ = cliente(httpx.Response(200, json={"errors": [{"message": "x" * 2000}]}))
    with pytest.raises(ContratoQuebrado) as e:
        DcscGraphql("https://x.test/graphql", c).coletar()
    assert len(str(e.value)) <= 520


def test_graphql_canario() -> None:
    est = est_graphql(rio={"rio_nivel": {"value": 1.0}})
    assert DcscGraphql(
        "https://x.test/graphql", cliente(httpx.Response(200, json=graphql([est])))[0]
    ).verificar_contrato()
    assert not DcscGraphql(
        "https://x.test/graphql", cliente(httpx.Response(200, json=graphql([])))[0]
    ).verificar_contrato()
    assert not DcscGraphql(
        "https://x.test/graphql", cliente(httpx.ConnectError("x"))[0]
    ).verificar_contrato()


# ---------- REST ----------


def test_rest_valor_zero_de_chuva_e_nivel_valido_e_none_nao() -> None:
    dados = {
        "dados": [
            {"timestamp": "2026-11-05T12:00:00Z", "rio_nivel_m": 0, "chuva_acumulada_mm": None}
        ]
    }
    leituras = norm_rest("DCSC-00043", dados)
    assert [(x.variavel, x.valor) for x in leituras] == [(Variavel.NIVEL_M, 0.0)]


def test_rest_lista_vazia_de_dados_nao_e_erro_e_ponto_nulo_e_contrato_quebrado() -> None:
    assert norm_rest("DCSC-00043", {"dados": []}) == []
    with pytest.raises(ContratoQuebrado):
        norm_rest("DCSC-00043", {"dados": [None]})


def test_rest_timestamp_invalido_e_contrato_quebrado() -> None:
    with pytest.raises(ContratoQuebrado):
        norm_rest("DCSC-00043", {"dados": [{"timestamp": "ontem", "rio_nivel_m": 1.0}]})


def test_rest_consulta_em_horario_de_brasilia_e_pede_a_estacao_certa() -> None:
    c, vistas = cliente(httpx.Response(200, json={"dados": []}))
    DcscRest("https://x.test/", ["DCSC-00043"], c).coletar(T0 - timedelta(hours=2), T0)
    p = vistas[0].url.params
    assert (p["codigo"], p["data_inicial"], p["data_final"]) == (
        "DCSC-00043",
        "2026-11-05T07:00-0300",
        "2026-11-05T09:00-0300",
    )
    assert vistas[0].url.path == "/api/estacoes/dados"


def test_rest_estacao_fora_do_ar_nao_interrompe_as_demais() -> None:
    def resposta(req: httpx.Request) -> httpx.Response:
        if req.url.params["codigo"] == "DCSC-00021":
            return httpx.Response(503)
        dados = [{"timestamp": "2026-11-05T11:00:00Z", "rio_nivel_m": 1.5}]
        return httpx.Response(200, json={"dados": dados})

    c, _ = cliente(resposta)
    leituras = DcscRest("https://x.test", ["DCSC-00021", "DCSC-00043"], c).coletar(
        T0 - timedelta(hours=2), T0
    )
    assert [x.estacao_codigo for x in leituras] == ["DCSC-00043"]


def test_rest_contrato_quebrado_de_uma_estacao_sobe_para_o_log_de_coleta() -> None:
    c, _ = cliente(httpx.Response(200, json={"outro": 1}))
    with pytest.raises(ContratoQuebrado):
        DcscRest("https://x.test", ["DCSC-00043"], c).coletar(T0 - timedelta(hours=2), T0)


def test_rest_janela_padrao_e_as_ultimas_duas_horas_quando_nao_informada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, vistas = cliente(httpx.Response(200, json={"dados": []}))
    DcscRest("https://x.test", ["DCSC-00043"], c).coletar()
    ini, fim = (
        datetime.strptime(vistas[0].url.params[k], "%Y-%m-%dT%H:%M%z")
        for k in ("data_inicial", "data_final")
    )
    assert fim - ini in (
        timedelta(hours=2),
        timedelta(hours=2, minutes=-1),
        timedelta(hours=2, minutes=1),
    )


def test_rest_canario() -> None:
    ok, _ = cliente(httpx.Response(200, json={"dados": []}))
    assert DcscRest("https://x.test", ["DCSC-00043"], ok).verificar_contrato() is True
    ruim, _ = cliente(httpx.Response(200, json={}))
    assert DcscRest("https://x.test", ["DCSC-00043"], ruim).verificar_contrato() is False
    fora, _ = cliente(httpx.ConnectError("x"))
    assert DcscRest("https://x.test", ["DCSC-00043"], fora).verificar_contrato() is False


# ---------- barragens ----------


def barragem(**mudar: Any) -> dict[str, Any]:
    norte: dict[str, Any] = {
        "limites": {"minimo": 256.0},
        "ultimaLeitura": "2026-11-05T12:00:00+00:00",
        "historico": [
            {"timestamp": "2026-11-05T11:55:00+00:00", "nivel": 273.9567, "nivel_porc": 80}
        ],
        "comportas": {"galeria": True, "tulipa258": False, "tulipa264": True},
    }
    norte.update(mudar)
    return {"data": {"barragemNorte": norte}}


def test_barragem_altura_e_cota_menos_o_minimo_arredondada_em_milimetros() -> None:
    leituras = norm_barragem(barragem())
    h = next(x for x in leituras if x.variavel == Variavel.RESERVATORIO_M)
    assert h.valor == 17.957 and h.estacao_codigo == ESTACAO_BARRAGEM_NORTE


def test_barragem_sem_percentual_nao_gera_leitura_de_percentual() -> None:
    ponto = {"timestamp": "2026-11-05T11:55:00+00:00", "nivel": 270.0}
    leituras = norm_barragem(barragem(historico=[ponto]))
    assert Variavel.RESERVATORIO_PCT not in {x.variavel for x in leituras}


def test_barragem_comporta_que_nao_e_booleana_e_ignorada() -> None:
    leituras = norm_barragem(
        barragem(comportas={"galeria": "aberta", "tulipa258": 1, "tulipa264": None})
    )
    assert [x for x in leituras if x.variavel.value.startswith("comporta")] == []


def test_barragem_estado_das_comportas_usa_a_ultima_leitura_como_horario() -> None:
    comportas = [x for x in norm_barragem(barragem()) if x.variavel.value.startswith("comporta")]
    assert {x.medido_em for x in comportas} == {T0}


def test_barragem_historico_vazio_so_traz_comportas() -> None:
    leituras = norm_barragem(barragem(historico=[]))
    assert {x.variavel for x in leituras} == {
        Variavel.COMPORTA_GALERIA,
        Variavel.COMPORTA_TULIPA258,
        Variavel.COMPORTA_TULIPA264,
    }


@pytest.mark.parametrize(
    "mudanca",
    [
        {"limites": {}},
        {"limites": {"minimo": "alto"}},
        {"ultimaLeitura": "ontem"},
        {"historico": [{"timestamp": "2026-11-05T11:55:00+00:00"}]},
        {"historico": [{"timestamp": "x", "nivel": 270.0}]},
    ],
)
def test_barragem_campo_obrigatorio_ausente_ou_invalido_e_contrato_quebrado(mudanca: dict) -> None:
    with pytest.raises(ContratoQuebrado):
        norm_barragem(barragem(**mudanca))


def test_barragem_rede_e_canario() -> None:
    c, vistas = cliente(httpx.Response(200, json=barragem()))
    adaptador = DcscBarragens("https://x.test/", c)
    assert adaptador.verificar_contrato() is True
    assert vistas[0].url.path == "/api/barragens"
    erro, _ = cliente(httpx.Response(500))
    with pytest.raises(FonteIndisponivel):
        DcscBarragens("https://x.test", erro).coletar()
    assert DcscBarragens("https://x.test", erro).verificar_contrato() is False


# ---------- Open-Meteo ----------


def test_forecast_sem_probabilidade_na_resposta_deixa_none() -> None:
    resp = {"hourly": {"time": ["2026-11-05T13:00"], "precipitation": [2.0]}}
    prev = normalizar_forecast("DCSC-00043", resp, T0)
    assert prev[0].probabilidade is None and prev[0].modelo_fonte == MODELO_FORECAST
    assert prev[0].valido_para == datetime(2026, 11, 5, 13, tzinfo=UTC)


def test_forecast_probabilidade_nula_pontual_e_chuva_zero_sao_preservadas() -> None:
    resp = {
        "hourly": {
            "time": ["2026-11-05T13:00", "2026-11-05T14:00"],
            "precipitation": [0.0, 1.5],
            "precipitation_probability": [None, 40],
        }
    }
    prev = normalizar_forecast("DCSC-00043", resp, T0)
    assert [(p.chuva_mm, p.probabilidade) for p in prev] == [(0.0, None), (1.5, 40.0)]


def test_archive_horas_em_utc_e_chuva_nula_ignorada() -> None:
    resp = {
        "hourly": {"time": ["2026-11-05T00:00", "2026-11-05T01:00"], "precipitation": [None, 0.0]}
    }
    leituras = normalizar_archive("DCSC-00043", resp)
    assert [(x.medido_em, x.valor) for x in leituras] == [
        (datetime(2026, 11, 5, 1, tzinfo=UTC), 0.0)
    ]


def test_archive_sem_hourly_e_contrato_quebrado() -> None:
    with pytest.raises(ContratoQuebrado):
        normalizar_archive("X", {"daily": {}})


def forecast_ok() -> dict[str, Any]:
    return json.loads((FIX / "openmeteo_forecast.json").read_text())


def test_previsao_de_um_ponto_fora_do_ar_nao_derruba_os_demais() -> None:
    def resposta(req: httpx.Request) -> httpx.Response:
        if req.url.params["latitude"] == "1.0":
            return httpx.Response(500)
        return httpx.Response(200, json=forecast_ok())

    c, _ = cliente(resposta)
    om = OpenMeteo("https://f.test", "https://a.test", c)
    prev = om.previsao([("A", 1.0, 1.0), ("B", 2.0, 2.0)])
    assert {p.estacao_codigo for p in prev} == {"B"} and len(prev) == 2


def test_previsao_pede_utc_e_os_dias_pedidos() -> None:
    c, vistas = cliente(httpx.Response(200, json=forecast_ok()))
    OpenMeteo("https://f.test", "https://a.test", c).previsao([("A", -27.0, -49.6)], dias=2)
    p = vistas[0].url.params
    assert (p["timezone"], p["forecast_days"], p["latitude"]) == ("UTC", "2", "-27.0")


def test_historico_pede_o_periodo_e_uma_falha_interrompe_a_carga() -> None:
    c, vistas = cliente(httpx.Response(200, json={"hourly": {"time": [], "precipitation": []}}))
    om = OpenMeteo("https://f.test", "https://a.test", c)
    om.historico([("A", 1.0, 2.0)], date(2026, 1, 1), date(2026, 1, 31))
    assert (vistas[0].url.params["start_date"], vistas[0].url.params["end_date"]) == (
        "2026-01-01",
        "2026-01-31",
    )
    erro, _ = cliente(httpx.Response(429))
    with pytest.raises(FonteIndisponivel):
        OpenMeteo("https://f.test", "https://a.test", erro).historico(
            [("A", 1.0, 2.0)], date(2026, 1, 1), date(2026, 1, 2)
        )


def test_openmeteo_canario() -> None:
    ponto = ("A", 1.0, 2.0)
    ok, _ = cliente(httpx.Response(200, json=forecast_ok()))
    assert OpenMeteo("https://f.test", "https://a.test", ok).verificar_contrato(ponto) is True
    vazio, _ = cliente(httpx.Response(200, json={"hourly": {"time": [], "precipitation": []}}))
    assert OpenMeteo("https://f.test", "https://a.test", vazio).verificar_contrato(ponto) is False
    quebrado, _ = cliente(httpx.Response(200, json={}))
    assert (
        OpenMeteo("https://f.test", "https://a.test", quebrado).verificar_contrato(ponto) is False
    )
    fora, _ = cliente(httpx.ConnectError("x"))
    assert OpenMeteo("https://f.test", "https://a.test", fora).verificar_contrato(ponto) is False
