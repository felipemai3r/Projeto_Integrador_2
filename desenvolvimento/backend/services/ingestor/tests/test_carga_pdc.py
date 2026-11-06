import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from common.models import Leitura
from common.seed import semear
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ingestor.adapters.pdc import Pdc
from ingestor.carga_pdc import carregar

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "pdc_readings.json").read_text())


def pdc_falso(janelas_vistas: list[tuple[str, str]], falhar_na: int | None = None) -> Pdc:
    def responder(req: httpx.Request) -> httpx.Response:
        janelas_vistas.append((req.url.params["from"], req.url.params["to"]))
        if falhar_na is not None and len(janelas_vistas) == falhar_na:
            return httpx.Response(500)
        return httpx.Response(200, json={"data": FIXTURE["peu001"]["data"], "next_cursor": None})

    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    return Pdc("https://pdc.exemplo.test", "chave-ficticia", cliente=cliente, intervalo_min_s=0)


def test_carga_grava_por_janela_e_reexecutar_nao_duplica(s: Session) -> None:
    semear(s)
    s.commit()
    vistas: list[tuple[str, str]] = []
    pdc = pdc_falso(vistas)
    args = {"desde": date(2026, 11, 1), "ate": datetime(2026, 11, 5, tzinfo=UTC)}
    totais = carregar(pdc, estacoes=["DC-PEU-001"], dias_janela=2, **args)
    # 4 dias em janelas de 2: duas consultas; o mesmo conteudo nas duas so conta uma vez
    assert len(vistas) == 2 and vistas[0][1] == vistas[1][0]
    assert totais == {"DCSC-00174": 4}
    assert carregar(pdc, estacoes=["DCSC-00174"], dias_janela=2, **args) == {"DCSC-00174": 0}
    assert s.scalar(select(func.count()).select_from(Leitura)) == 4


def test_janela_com_falha_nao_interrompe_a_carga(s: Session) -> None:
    semear(s)
    s.commit()
    vistas: list[tuple[str, str]] = []
    pdc = pdc_falso(vistas, falhar_na=1)
    totais = carregar(
        pdc,
        desde=date(2026, 11, 1),
        ate=datetime(2026, 11, 5, tzinfo=UTC),
        estacoes=["DC-PEU-001"],
        dias_janela=2,
    )
    assert len(vistas) == 2 and totais == {"DCSC-00174": 4}


def test_tamanho_de_janela_invalido() -> None:
    with pytest.raises(ValueError, match="dias_janela"):
        carregar(pdc_falso([]), dias_janela=32)
