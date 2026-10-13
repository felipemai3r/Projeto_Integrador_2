from datetime import UTC, datetime, timedelta

from common.models import Correlacao, Estacao
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _linha(
    s: Session, alvo: str, ponto: str, expl: str, r: float, p: float, quando: datetime
) -> None:
    ids = {e.codigo: e.id for e in s.scalars(select(Estacao))}
    s.add(
        Correlacao(
            estacao_alvo_id=ids[alvo],
            ponto_id=ids[ponto],
            explicativa=expl,
            janela_chuva_h=3,
            melhor_defasagem_h=2,
            r=r,
            ic_inf=r - 0.1,
            ic_sup=r + 0.1,
            p_valor=p,
            horas_validas=900,
            curva=[],
            metodo="teste",
            periodo_inicio=quando - timedelta(days=90),
            periodo_fim=quando,
            calculado_em=quando,
        )
    )


def test_devolve_so_a_rodada_mais_recente(client: TestClient, s: Session) -> None:
    semear(s)
    s.commit()
    velha = datetime(2026, 10, 1, tzinfo=UTC)
    nova = datetime(2026, 10, 12, tzinfo=UTC)
    _linha(s, "DCSC-00043", "DCSC-00037", "chuva_bruta", 0.1, 0.5, velha)
    _linha(s, "DCSC-00043", "DCSC-00037", "chuva_bruta", 0.34, 0.005, nova)
    s.commit()
    corpo = client.get("/api/correlacao").json()
    assert len(corpo) == 1
    assert corpo[0]["r"] == 0.34
    assert corpo[0]["sinal_claro"] is True


def test_sem_sinal_e_dito_com_clareza(client: TestClient, s: Session) -> None:
    semear(s)
    s.commit()
    quando = datetime(2026, 10, 12, tzinfo=UTC)
    _linha(s, "DCSC-00043", "DCSC-00021", "chuva_sem_local", 0.07, 0.46, quando)
    s.commit()
    item = client.get("/api/correlacao").json()[0]
    assert item["sinal_claro"] is False
    assert "acaso" in item["leitura"]


def test_sem_analise_devolve_lista_vazia_e_estacao_invalida_404(
    client: TestClient, s: Session
) -> None:
    semear(s)
    s.commit()
    assert client.get("/api/correlacao").json() == []
    assert client.get("/api/correlacao", params={"estacao": "XXX"}).status_code == 404
