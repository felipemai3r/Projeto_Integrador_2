import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from common.enums import Variavel
from common.models import Estacao, Fonte, Leitura
from common.seed import semear
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ingestor.adapters.pdc import CODIGOS, Pdc, janelas, normalizar
from ingestor.erros import ContratoQuebrado, FonteIndisponivel
from ingestor.gravar import gravar

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "pdc_readings.json").read_text())
CHAVE = "chave-ficticia-de-teste"
BASE = "https://pdc.exemplo.test/stations-api"
AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


class Servidor:
    """Cliente httpx falso: devolve as respostas na ordem e guarda as requisicoes."""

    def __init__(self, respostas: list[httpx.Response | Exception] | Any) -> None:
        self.respostas = respostas
        self.requisicoes: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requisicoes.append(req)
        if callable(self.respostas):
            return self.respostas(req)
        r = self.respostas[min(len(self.requisicoes), len(self.respostas)) - 1]
        if isinstance(r, Exception):
            raise r
        return r


def pdc_com(
    servidor: Servidor, esperas: list[float] | None = None, **kw: Any
) -> tuple[Pdc, list[float]]:
    dormidas: list[float] = [] if esperas is None else esperas
    cliente = httpx.Client(transport=httpx.MockTransport(servidor))
    kw.setdefault("intervalo_min_s", 0.0)
    return Pdc(BASE, CHAVE, cliente=cliente, dormir=dormidas.append, **kw), dormidas


def json_resp(corpo: Any, status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(status, json=corpo, headers=headers)


# --- normalizar ----------------------------------------------------------------------------


def test_creche_do_painel_vai_para_a_estacao_dcsc_00174() -> None:
    leituras = normalizar(FIXTURE["peu001"])
    assert {x.estacao_codigo for x in leituras} == {"DCSC-00174"}
    assert CODIGOS["DC-PEU-001"] == "DCSC-00174"


def test_medido_em_e_created_at_e_nao_o_sta_timestamp_deslocado() -> None:
    reg = FIXTURE["peu001"]["data"][0]
    assert reg["sta_timestamp"] == "2026-11-04T16:07:17+00:00"  # hora local rotulada como UTC
    leituras = normalizar({"data": [reg]})
    assert {x.medido_em for x in leituras} == {datetime(2026, 11, 4, 19, 7, 18, 19645, tzinfo=UTC)}


def test_mapeia_nivel_e_chuva_da_ultima_hora() -> None:
    leituras = normalizar(FIXTURE["peu001"])
    por_var = {v: [x for x in leituras if x.variavel == v] for v in Variavel}
    assert [(x.valor, x.unidade) for x in por_var[Variavel.NIVEL_M]] == [(0.81, "m"), (0.8, "m")]
    assert [(x.valor, x.unidade) for x in por_var[Variavel.CHUVA_H001_MM]] == [
        (0.4, "mm"),
        (0.8, "mm"),
    ]
    # janela movel de 1h nunca pode ser gravada como incremento de 5 min
    assert por_var[Variavel.CHUVA_ACUMULADA_MM] == []


def test_campos_nulos_sao_ignorados_e_zero_nao() -> None:
    # DC-PEU-002 mede so chuva (river_level nulo) e na 2a leitura rainfall_1h tambem e nulo
    leituras = normalizar(FIXTURE["peu002_pagina1"])
    assert [(x.variavel, x.valor) for x in leituras] == [(Variavel.CHUVA_H001_MM, 0.0)]
    assert leituras[0].estacao_codigo == "DC-PEU-002"


@pytest.mark.parametrize("codigo", ["DC-PEU-002", "DC-PEU-003", "DC-PEU-004", "DCSC-00037"])
def test_river_level_de_estacao_sem_regua_e_ignorado(codigo: str) -> None:
    # essas estacoes mandam river_level espurio (0 ou ate 42 m) embora so medam chuva
    reg = {
        "sta_code": codigo,
        "created_at": "2026-09-20T12:00:00+00:00",
        "river_level": 17.7,
        "rainfall_1h": 1.2,
    }
    leituras = normalizar({"data": [reg]})
    assert [(x.variavel, x.valor) for x in leituras] == [(Variavel.CHUVA_H001_MM, 1.2)]


def test_river_level_das_estacoes_com_regua_e_mantido() -> None:
    regs = [
        {"sta_code": c, "created_at": "2026-09-20T12:00:00+00:00", "river_level": 1.5}
        for c in ("DC-PEU-001", "DCSC-00043")
    ]
    leituras = normalizar({"data": regs})
    assert {(x.estacao_codigo, x.variavel) for x in leituras} == {
        ("DCSC-00174", Variavel.NIVEL_M),
        ("DCSC-00043", Variavel.NIVEL_M),
    }


def test_bruto_guarda_o_registro_sem_os_campos_nulos() -> None:
    leitura = normalizar({"data": [FIXTURE["peu001"]["data"][0]]})[0]
    assert leitura.bruto is not None
    assert "rainfall_3h" not in leitura.bruto and "temperature" not in leitura.bruto
    assert leitura.bruto["sta_code"] == "DC-PEU-001" and leitura.bruto["rainfall_1h"] == 0.4


@pytest.mark.parametrize(
    "resposta",
    [
        {},
        {"data": None},
        {"data": [1]},
        {"data": [{"created_at": "2026-11-04T19:00:00+00:00", "river_level": 1.0}]},  # sem sta_code
        {"data": [{"sta_code": "DC-PEU-002", "temperature": 20}]},  # campos renomeados
        {"data": [{"sta_code": "DC-PEU-002", "rainfall_1h": 0}]},  # sem created_at
        {"data": [{"sta_code": "DC-PEU-002", "rainfall_1h": 0, "created_at": "ontem"}]},
        {"data": [{"sta_code": "DC-PEU-002", "rainfall_1h": 0, "created_at": "2026-11-04T19:00"}]},
    ],
)
def test_resposta_fora_do_contrato_levanta_contrato_quebrado(resposta: dict[str, Any]) -> None:
    with pytest.raises(ContratoQuebrado):
        normalizar(resposta)


def test_codigo_desconhecido_passa_sem_traducao() -> None:
    reg = {"sta_code": "XYZ", "rainfall_1h": 1, "created_at": "2026-11-04T19:00:00+00:00"}
    assert normalizar({"data": [reg]})[0].estacao_codigo == "XYZ"


def test_janelas_cobrem_o_intervalo_sem_passar_de_31_dias() -> None:
    ini = datetime(2025, 9, 13, tzinfo=UTC)
    fim = ini + timedelta(days=70)
    lista = list(janelas(ini, fim))
    assert lista[0][0] == ini and lista[-1][1] == fim
    assert all(b - a <= timedelta(days=31) for a, b in lista)
    assert all(lista[i][1] == lista[i + 1][0] for i in range(len(lista) - 1))
    assert len(lista) == 3
    assert list(janelas(fim, ini)) == []


# --- paginacao, taxa e erros ---------------------------------------------------------------


def paginas_da_fixture(req: httpx.Request) -> httpx.Response:
    cursor = req.url.params.get("cursor")
    chave = {
        None: "peu002_pagina1",
        FIXTURE["peu002_pagina1"]["next_cursor"]: "peu002_pagina2",
        FIXTURE["peu002_pagina2"]["next_cursor"]: "peu002_pagina3",
    }[cursor]
    return json_resp(FIXTURE[chave])


def test_pagina_por_cursor_e_descarta_a_linha_repetida_entre_paginas() -> None:
    servidor = Servidor(paginas_da_fixture)
    pdc, _ = pdc_com(servidor)
    ini = datetime(2026, 11, 4, 19, 5, tzinfo=UTC)
    leituras = pdc.coletar_estacao("DC-PEU-002", ini, ini + timedelta(minutes=15), limite=2)
    assert len(servidor.requisicoes) == 3
    # 3 linhas distintas (o cursor e inclusivo); a do meio tem rainfall_1h nulo
    assert [x.valor for x in leituras] == [0.0, 0.0]
    primeira = servidor.requisicoes[0]
    assert primeira.headers["x-api-key"] == CHAVE
    assert primeira.url.path.endswith("/readings")
    assert dict(primeira.url.params) == {
        "code": "DC-PEU-002",
        "from": "2026-11-04T19:05:00Z",
        "to": "2026-11-04T19:20:00Z",
        "limit": "2",
    }
    assert servidor.requisicoes[1].url.params["cursor"] == FIXTURE["peu002_pagina1"]["next_cursor"]


def test_cursor_que_nao_avanca_nao_gera_laco_infinito() -> None:
    pagina = {"data": FIXTURE["peu001"]["data"][:1], "next_cursor": "2026-11-04T19:07:18+00:00"}
    servidor = Servidor(lambda req: json_resp(pagina))
    pdc, _ = pdc_com(servidor)
    ini = datetime(2026, 11, 4, 19, tzinfo=UTC)
    leituras = pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1))
    assert len(servidor.requisicoes) == 2 and len(leituras) == 2


def test_limite_de_pagina_menor_que_2_e_recusado() -> None:
    pdc, _ = pdc_com(Servidor([]))
    ini = datetime(2026, 11, 4, tzinfo=UTC)
    with pytest.raises(ValueError, match="limite"):
        pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1), limite=1)


def test_aceita_o_codigo_do_nosso_banco_para_a_creche() -> None:
    servidor = Servidor([json_resp({"data": [], "next_cursor": None})])
    pdc, _ = pdc_com(servidor)
    ini = datetime(2026, 11, 4, tzinfo=UTC)
    pdc.coletar_estacao("DCSC-00174", ini, ini + timedelta(hours=1))
    assert servidor.requisicoes[0].url.params["code"] == "DC-PEU-001"


def test_periodo_longo_vira_varias_consultas_de_no_maximo_31_dias() -> None:
    servidor = Servidor(lambda req: json_resp({"data": [], "next_cursor": None}))
    pdc, _ = pdc_com(servidor)
    ini = datetime(2025, 9, 13, tzinfo=UTC)
    pdc.coletar_estacao("DC-PEU-003", ini, ini + timedelta(days=70))
    assert len(servidor.requisicoes) == 3
    for req in servidor.requisicoes:
        de = datetime.fromisoformat(req.url.params["from"])
        ate = datetime.fromisoformat(req.url.params["to"])
        assert ate - de <= timedelta(days=31)


def test_429_espera_e_tenta_de_novo() -> None:
    servidor = Servidor(
        [
            json_resp({"error": "rate"}, 429, **{"retry-after": "7"}),
            json_resp({"error": "rate"}, 429),
            json_resp({"data": FIXTURE["peu001"]["data"], "next_cursor": None}),
        ]
    )
    pdc, dormidas = pdc_com(servidor)
    ini = datetime(2026, 11, 4, 19, tzinfo=UTC)
    leituras = pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1))
    assert len(leituras) == 4
    assert dormidas == [7.0, 10.0]  # Retry-After; depois recuo progressivo


def test_429_persistente_vira_fonte_indisponivel() -> None:
    servidor = Servidor(lambda req: json_resp({"error": "rate"}, 429))
    pdc, dormidas = pdc_com(servidor)
    ini = datetime(2026, 11, 4, tzinfo=UTC)
    with pytest.raises(FonteIndisponivel, match="429"):
        pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1))
    assert len(servidor.requisicoes) == 4 and len(dormidas) == 3


def test_espaca_as_chamadas_para_respeitar_120_por_minuto() -> None:
    servidor = Servidor(lambda req: json_resp({"data": [], "next_cursor": None}))
    hora = [100.0]
    dormidas: list[float] = []
    cliente = httpx.Client(transport=httpx.MockTransport(servidor))
    pdc = Pdc(BASE, CHAVE, cliente=cliente, dormir=dormidas.append, relogio=lambda: hora[0])
    ini = datetime(2026, 11, 4, tzinfo=UTC)
    for _ in range(3):
        pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1))
    assert len(dormidas) == 2 and all(d >= 0.5 for d in dormidas)  # a 1a chamada nao espera


def test_chave_recusada_e_erro_http_viram_fonte_indisponivel_sem_vazar_a_chave() -> None:
    ini = datetime(2026, 11, 4, tzinfo=UTC)
    for status in (401, 403, 500):
        pdc, _ = pdc_com(Servidor([json_resp({"error": "x"}, status)]))
        with pytest.raises(FonteIndisponivel) as e:
            pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1))
        assert CHAVE not in str(e.value) and str(status) in str(e.value)


def test_falha_de_rede_e_json_invalido_viram_fonte_indisponivel() -> None:
    ini = datetime(2026, 11, 4, tzinfo=UTC)
    for resposta in (httpx.ConnectError("sem rede"), httpx.Response(200, text="<html>")):
        pdc, _ = pdc_com(Servidor([resposta]))
        with pytest.raises(FonteIndisponivel):
            pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1))


def test_corpo_que_nao_e_objeto_e_contrato_quebrado() -> None:
    pdc, _ = pdc_com(Servidor([json_resp([1, 2])]))
    ini = datetime(2026, 11, 4, tzinfo=UTC)
    with pytest.raises(ContratoQuebrado):
        pdc.coletar_estacao("DC-PEU-001", ini, ini + timedelta(hours=1))


def test_estacao_fora_do_ar_nao_interrompe_as_demais() -> None:
    def responder(req: httpx.Request) -> httpx.Response:
        if req.url.params["code"] == "DC-PEU-002":
            return json_resp({"error": "boom"}, 500)
        return json_resp({"data": FIXTURE["peu001"]["data"], "next_cursor": None})

    pdc, _ = pdc_com(Servidor(responder), estacoes=["DC-PEU-001", "DC-PEU-002", "DCSC-00043"])
    leituras = pdc.coletar(AGORA - timedelta(hours=1), AGORA)
    assert len(leituras) == 8  # duas estacoes responderam, 4 leituras cada


def test_todas_as_estacoes_fora_do_ar_nao_vira_coleta_vazia() -> None:
    pdc, _ = pdc_com(Servidor(lambda req: json_resp({"error": "boom"}, 500)))
    with pytest.raises(FonteIndisponivel, match="nenhuma estacao"):
        pdc.coletar(AGORA - timedelta(hours=1), AGORA)


def test_coleta_padrao_e_a_ultima_hora_de_todas_as_estacoes_mapeadas() -> None:
    servidor = Servidor(lambda req: json_resp({"data": [], "next_cursor": None}))
    pdc, _ = pdc_com(servidor)
    pdc.coletar()
    codigos = [r.url.params["code"] for r in servidor.requisicoes]
    assert codigos == list(CODIGOS)
    de = datetime.fromisoformat(servidor.requisicoes[0].url.params["from"])
    ate = datetime.fromisoformat(servidor.requisicoes[0].url.params["to"])
    assert ate - de == timedelta(hours=1)


def test_verificar_contrato() -> None:
    latest = {"data": FIXTURE["peu001"]["data"]}
    pdc, _ = pdc_com(Servidor([json_resp(latest)]))
    assert pdc.verificar_contrato() is True
    pdc, _ = pdc_com(Servidor([json_resp({"data": [{"sta_code": "A", "created_at": "x"}]})]))
    assert pdc.verificar_contrato() is False
    pdc, _ = pdc_com(Servidor([json_resp({"error": "x"}, 500)]))
    assert pdc.verificar_contrato() is False


# --- gravacao ------------------------------------------------------------------------------


def test_grava_na_fonte_nova_e_marca_o_pico_espurio_como_suspeito(s: Session) -> None:
    semear(s)
    s.commit()
    leituras = normalizar(FIXTURE["pico_00043"])
    inseridas, descartadas = gravar(s, "pdc_municipal", leituras, AGORA)
    s.commit()
    assert (inseridas, descartadas) == (6, 0)
    fonte = s.scalar(select(Fonte).where(Fonte.codigo == "pdc_municipal"))
    chuvas = {
        x.valor: x for x in s.scalars(select(Leitura).where(Leitura.variavel == "chuva_h001_mm"))
    }
    assert chuvas[248.28].qualidade == "suspeita"
    assert chuvas[0.2].qualidade == "ok"
    assert chuvas[248.28].fonte_id == fonte.id  # type: ignore[union-attr]


def test_reexecutar_a_coleta_nao_duplica(s: Session) -> None:
    semear(s)
    s.commit()
    leituras = normalizar(FIXTURE["pico_00043"]) + normalizar(FIXTURE["peu001"])
    assert gravar(s, "pdc_municipal", leituras, AGORA)[0] == 6 + 4
    s.commit()
    assert gravar(s, "pdc_municipal", leituras, AGORA)[0] == 0
    s.commit()
    assert s.scalar(select(func.count()).select_from(Leitura)) == 10


def test_leituras_da_creche_e_das_estacoes_novas_caem_nas_estacoes_certas(s: Session) -> None:
    semear(s)
    s.commit()
    desconhecida = {"sta_code": "XYZ", "rainfall_1h": 1, "created_at": "2026-11-04T19:00:00+00:00"}
    leituras = (
        normalizar(FIXTURE["peu001"])
        + normalizar(FIXTURE["peu002_pagina1"])
        + normalizar({"data": [desconhecida]})
    )
    inseridas, _ = gravar(s, "pdc_municipal", leituras, AGORA)  # a XYZ nao existe no banco
    s.commit()
    assert inseridas == 5
    por_estacao = dict(
        s.execute(
            select(Estacao.codigo, func.count())
            .join(Leitura, Leitura.estacao_id == Estacao.id)
            .group_by(Estacao.codigo)
        ).all()
    )
    assert por_estacao == {"DCSC-00174": 4, "DC-PEU-002": 1}
