import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from common.enums import Variavel

from ingestor.adapters.dcsc_barragens import normalizar as norm_barragem
from ingestor.adapters.openmeteo import normalizar_archive, normalizar_forecast
from ingestor.erros import ContratoQuebrado

FIX = Path(__file__).parent / "fixtures"


def carregar(nome: str) -> dict:
    return json.loads((FIX / nome).read_text())


def test_barragem_converte_cota_absoluta_para_altura_sobre_o_fundo() -> None:
    leituras = norm_barragem(carregar("dcsc_barragens.json"))
    alturas = [x for x in leituras if x.variavel == Variavel.RESERVATORIO_M]
    assert alturas[0].valor == pytest.approx(17.95)  # 273,95 - 256


def test_barragem_traz_percentual_e_comportas() -> None:
    leituras = norm_barragem(carregar("dcsc_barragens.json"))
    por_var = {x.variavel: x.valor for x in leituras if x.variavel.value.startswith("comporta")}
    assert por_var == {
        Variavel.COMPORTA_GALERIA: 1.0,
        Variavel.COMPORTA_TULIPA258: 0.0,
        Variavel.COMPORTA_TULIPA264: 1.0,
    }
    assert any(x.variavel == Variavel.RESERVATORIO_PCT for x in leituras)


def test_barragem_com_formato_diferente_e_contrato_quebrado() -> None:
    with pytest.raises(ContratoQuebrado):
        norm_barragem({"data": {}})


def test_forecast_normaliza_e_ignora_hora_sem_valor() -> None:
    gerado = datetime(2026, 10, 12, 0, tzinfo=UTC)
    prev = normalizar_forecast("DCSC-00037", carregar("openmeteo_forecast.json"), gerado)
    assert [p.chuva_mm for p in prev] == [0.0, 1.4]
    assert prev[1].probabilidade == 35.0
    assert prev[1].valido_para == datetime(2026, 10, 12, 1, tzinfo=UTC)


def test_forecast_sem_hourly_e_contrato_quebrado() -> None:
    with pytest.raises(ContratoQuebrado):
        normalizar_forecast("X", {}, datetime.now(UTC))


def test_archive_vira_chuva_horaria() -> None:
    leituras = normalizar_archive("DCSC-00037", carregar("openmeteo_archive.json"))
    assert [x.valor for x in leituras] == [0.3, 12.5]
    assert all(x.variavel == Variavel.CHUVA_H001_MM for x in leituras)
