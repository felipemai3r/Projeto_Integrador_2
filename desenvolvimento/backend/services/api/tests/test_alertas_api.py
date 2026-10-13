from datetime import UTC, datetime, timedelta

from common.models import Alerta, Estacao
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_lista_alertas_vigentes_e_historico(client: TestClient, s: Session) -> None:
    semear(s)
    s.commit()
    est = s.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one()
    t0 = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
    s.add_all(
        [
            Alerta(
                estacao_id=est.id,
                faixa_anterior="normal",
                faixa_nova="atencao",
                severidade="atencao",
                origem="observado",
                criado_em=t0,
                encerrado_em=t0 + timedelta(hours=1),
            ),
            Alerta(
                estacao_id=est.id,
                faixa_anterior="atencao",
                faixa_nova="alerta",
                severidade="alerta",
                origem="observado",
                criado_em=t0 + timedelta(hours=1),
            ),
        ]
    )
    s.commit()

    vigentes = client.get("/api/alertas", params={"vigentes": True}).json()
    assert [a["faixa_nova"] for a in vigentes] == ["alerta"]
    assert vigentes[0]["vigente"] is True and vigentes[0]["sobe"] is True
    assert vigentes[0]["origem"] == "observado"
    assert "fonte oficial" in vigentes[0]["aviso"].lower()

    historico = client.get("/api/alertas").json()
    assert [a["faixa_nova"] for a in historico] == ["alerta", "atencao"]
    assert historico[1]["vigente"] is False
