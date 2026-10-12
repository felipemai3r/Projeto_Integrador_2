from datetime import timedelta

import pytest
from common.enums import Variavel
from common.models import Fonte, Leitura
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tempo_api import AGORA


def _id_estacao(s: Session, codigo: str) -> int:
    from common.models import Estacao

    return s.scalars(select(Estacao.id).where(Estacao.codigo == codigo)).one()


def _fonte(s: Session, codigo: str) -> int:
    return s.scalars(select(Fonte.id).where(Fonte.codigo == codigo)).one()


def _nivel(s: Session, codigo: str, valores: list[float], ultimo_ha_min: int = 0) -> None:
    """Grava leituras de 5 em 5 min terminando `ultimo_ha_min` minutos antes de AGORA."""
    est, fonte = _id_estacao(s, codigo), _fonte(s, "dcsc_graphql")
    n = len(valores)
    for i, v in enumerate(valores):
        s.add(
            Leitura(
                estacao_id=est,
                variavel=Variavel.NIVEL_M.value,
                valor=v,
                unidade="m",
                medido_em=AGORA - timedelta(minutes=ultimo_ha_min + 5 * (n - 1 - i)),
                fonte_id=fonte,
                qualidade="ok",
            )
        )
    s.commit()


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def test_saude(client: TestClient) -> None:
    assert client.get("/api/saude").json() == {"status": "ok"}


def test_lista_estacoes_com_limiares(client: TestClient, base: Session) -> None:
    corpo = client.get("/api/estacoes").json()
    assert len(corpo) == 8
    indios = next(e for e in corpo if e["codigo"] == "DCSC-00043")
    assert indios["limiares"] == {"observacao": 4.0, "atencao": 4.5, "alerta": 5.5}
    sem_limiar = next(e for e in corpo if e["codigo"] == "DCSC-00037")
    assert sem_limiar["limiares"]["alerta"] is None


def test_atual_classifica_e_calcula_tendencia(client: TestClient, base: Session) -> None:
    # 2 h de subida constante: de 4,20 m a 4,62 m (+21 cm/h)
    valores = [4.20 + 0.42 * i / 24 for i in range(25)]
    _nivel(base, "DCSC-00043", valores)
    r = client.get("/api/estacoes/DCSC-00043/atual").json()
    assert r["estado"] == "ok"
    assert r["nivel_m"] == pytest.approx(4.62)
    assert r["faixa"] == "atencao"
    assert r["tendencia"] == "subindo"
    assert r["taxa_cm_h"] == pytest.approx(21.0, abs=0.5)
    assert r["fonte"] == "dcsc_graphql"
    assert r["medido_em"]


def test_dado_velho_fica_desatualizado_mas_continua_visivel(
    client: TestClient, base: Session
) -> None:
    _nivel(base, "DCSC-00043", [3.1], ultimo_ha_min=90)
    r = client.get("/api/estacoes/DCSC-00043/atual").json()
    assert r["estado"] == "desatualizado"
    assert r["nivel_m"] == pytest.approx(3.1)
    assert "desatualizado" in r["motivo"].lower()


def test_estacao_sem_leitura_e_indisponivel(client: TestClient, base: Session) -> None:
    r = client.get("/api/estacoes/DCSC-00174/atual").json()
    assert r["estado"] == "indisponivel"
    assert r["nivel_m"] is None and r["faixa"] is None


def test_leitura_suspeita_nao_e_a_atual(client: TestClient, base: Session) -> None:
    _nivel(base, "DCSC-00043", [1.8], ultimo_ha_min=10)
    est = _id_estacao(base, "DCSC-00043")
    base.add(
        Leitura(
            estacao_id=est,
            variavel="nivel_m",
            valor=9.9,
            unidade="m",
            medido_em=AGORA,
            fonte_id=_fonte(base, "dcsc_graphql"),
            qualidade="suspeita",
        )
    )
    base.commit()
    assert client.get("/api/estacoes/DCSC-00043/atual").json()["nivel_m"] == pytest.approx(1.8)


def test_estacao_inexistente_da_404(client: TestClient, base: Session) -> None:
    assert client.get("/api/estacoes/XXX/atual").status_code == 404
    assert client.get("/api/estacoes/XXX/serie").status_code == 404


def test_serie_agrega_por_passo(client: TestClient, base: Session) -> None:
    _nivel(base, "DCSC-00043", [1.0 + 0.01 * i for i in range(36)])  # 3 h de 5 em 5 min
    r = client.get("/api/estacoes/DCSC-00043/serie", params={"horas": 3, "passo_min": 15}).json()
    assert r["unidade"] == "m" and r["passo_min"] == 15
    assert 11 <= len(r["pontos"]) <= 13  # 36 pontos / 3 por balde de 15 min
    valores = [p["valor"] for p in r["pontos"]]
    assert valores == sorted(valores)


def test_serie_rejeita_parametros_invalidos(client: TestClient, base: Session) -> None:
    assert client.get("/api/estacoes/DCSC-00043/serie", params={"horas": 0}).status_code == 422
    assert client.get("/api/estacoes/DCSC-00043/serie", params={"variavel": "x"}).status_code == 422


def test_chuva_acumulada_por_janela(client: TestClient, base: Session) -> None:
    est, fonte = _id_estacao(base, "DCSC-00037"), _fonte(base, "dcsc_graphql")
    for var, v in (("chuva_h001_mm", 1.3), ("chuva_h024_mm", 1.5), ("chuva_h168_mm", 61.1)):
        base.add(
            Leitura(
                estacao_id=est,
                variavel=var,
                valor=v,
                unidade="mm",
                medido_em=AGORA - timedelta(minutes=3),
                fonte_id=fonte,
                qualidade="ok",
            )
        )
    base.commit()
    corpo = client.get("/api/chuva/acumulada").json()
    emma = next(e for e in corpo if e["estacao"] == "DCSC-00037")
    assert emma["estado"] == "ok"
    assert emma["acumulado_mm"]["1h"] == pytest.approx(1.3)
    assert emma["acumulado_mm"]["168h"] == pytest.approx(61.1)
    assert emma["acumulado_mm"]["3h"] is None
    sem_dado = next(e for e in corpo if e["estacao"] == "DCSC-00015")
    assert sem_dado["estado"] == "indisponivel"
