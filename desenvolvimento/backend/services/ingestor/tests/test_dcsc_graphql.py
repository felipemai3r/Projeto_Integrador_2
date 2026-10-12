import json
from pathlib import Path

import pytest
from common.enums import Variavel

from ingestor.adapters.dcsc_graphql import normalizar
from ingestor.erros import ContratoQuebrado

FIXTURE = Path(__file__).parent / "fixtures" / "dcsc_graphql.json"


@pytest.fixture
def resposta() -> dict:
    return json.loads(FIXTURE.read_text())


def test_normaliza_nivel_e_chuva_da_estacao_alvo(resposta: dict) -> None:
    leituras = [x for x in normalizar(resposta) if x.estacao_codigo == "DCSC-00043"]
    por_var = {x.variavel: x for x in leituras}
    assert por_var[Variavel.NIVEL_M].valor == pytest.approx(1.75)
    assert por_var[Variavel.NIVEL_M].unidade == "m"
    assert por_var[Variavel.CHUVA_H024_MM].valor == pytest.approx(0.4)
    assert por_var[Variavel.CHUVA_H168_MM].valor == pytest.approx(40.2)
    assert len(leituras) == 9  # nivel + 8 janelas de chuva


def test_estacao_sem_sensor_de_nivel_so_traz_chuva(resposta: dict) -> None:
    leituras = [x for x in normalizar(resposta) if x.estacao_codigo == "DCSC-00037"]
    assert Variavel.NIVEL_M not in {x.variavel for x in leituras}
    assert Variavel.CHUVA_H001_MM in {x.variavel for x in leituras}


def test_horario_vem_com_fuso(resposta: dict) -> None:
    leitura = normalizar(resposta)[0]
    assert leitura.medido_em.utcoffset() is not None


def test_estacao_sem_leitura_corrente_e_ignorada(resposta: dict) -> None:
    assert not [x for x in normalizar(resposta) if x.estacao_codigo == "DCSC-00999"]


def test_valor_nulo_da_fonte_nao_vira_leitura(resposta: dict) -> None:
    # a barragem (DCSC-00042) traz nivel e chuva nulos
    assert not [x for x in normalizar(resposta) if x.estacao_codigo == "DCSC-00042"]


def test_contrato_quebrado_e_detectado() -> None:
    with pytest.raises(ContratoQuebrado):
        normalizar({"data": {"outra_coisa": []}})
    with pytest.raises(ContratoQuebrado):
        normalizar({"data": {"tags_data": {"qualle_meteorologia": "nao e lista"}}})
