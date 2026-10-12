import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from common.enums import Variavel

from ingestor.adapters.dcsc_rest import _formatar, normalizar
from ingestor.erros import ContratoQuebrado

FIXTURE = Path(__file__).parent / "fixtures" / "dcsc_rest_dados.json"


def test_normaliza_serie_de_cinco_minutos() -> None:
    leituras = normalizar("DCSC-00043", json.loads(FIXTURE.read_text()))
    niveis = [x for x in leituras if x.variavel == Variavel.NIVEL_M]
    chuvas = [x for x in leituras if x.variavel == Variavel.CHUVA_ACUMULADA_MM]
    assert [x.valor for x in niveis] == [1.76, 1.76]  # terceiro ponto tem nivel nulo
    assert len(chuvas) == 3
    assert niveis[1].medido_em - niveis[0].medido_em == timedelta(minutes=5)


def test_formato_de_data_aceito_pela_fonte() -> None:
    dt = datetime(2026, 9, 18, 3, 0, tzinfo=UTC)
    assert _formatar(dt) == "2026-09-18T00:00-0300"


def test_resposta_sem_lista_dados_e_contrato_quebrado() -> None:
    with pytest.raises(ContratoQuebrado):
        normalizar("DCSC-00043", {"codigo": "DCSC-00043"})


def test_ponto_sem_timestamp_e_contrato_quebrado() -> None:
    with pytest.raises(ContratoQuebrado):
        normalizar("DCSC-00043", {"dados": [{"rio_nivel_m": 1.0}]})


def test_cota_da_barragem_nao_vira_nivel_de_rio() -> None:
    resposta = {"dados": [{"timestamp": "2026-10-12T21:00:00.000Z", "rio_nivel_m": 273.95}]}
    leituras = normalizar("DCSC-00042", resposta)
    assert [x.variavel for x in leituras] == [Variavel.RESERVATORIO_M]
