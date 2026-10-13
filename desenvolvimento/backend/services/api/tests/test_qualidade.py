from datetime import timedelta

from common.enums import StatusColeta
from common.models import Estacao, Fonte, Leitura, LogColeta
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tempo_api import AGORA


def _ids(s: Session) -> tuple[int, int]:
    est = s.scalars(select(Estacao.id).where(Estacao.codigo == "DCSC-00043")).one()
    fonte = s.scalars(select(Fonte.id).where(Fonte.codigo == "dcsc_rest")).one()
    return est, fonte


def _serie(s: Session, valores: list[float], passo_min: int = 5, termina_ha_min: int = 0) -> None:
    est, fonte = _ids(s)
    n = len(valores)
    for i, v in enumerate(valores):
        s.add(
            Leitura(
                estacao_id=est,
                variavel="nivel_m",
                valor=v,
                unidade="m",
                medido_em=AGORA - timedelta(minutes=termina_ha_min + passo_min * (n - 1 - i)),
                fonte_id=fonte,
                qualidade="ok",
            )
        )
    s.commit()


def _estacao(client: TestClient) -> dict:
    corpo = client.get("/api/qualidade").json()["estacoes"]
    return next(e for e in corpo if e["estacao"] == "DCSC-00043" and e["variavel"] == "nivel_m")


def test_cobertura_de_24h_completa(client: TestClient, s: Session) -> None:
    semear(s)
    s.commit()
    _serie(s, [1.0 + 0.001 * i for i in range(288)])  # 24 h de 5 em 5 min
    e = _estacao(client)
    assert e["cobertura_24h_pct"] >= 99.0
    assert e["lacunas_7d"] == 0 and e["possivelmente_travado"] is False


def test_lacuna_e_detectada_e_medida(client: TestClient, s: Session) -> None:
    semear(s)
    s.commit()
    _serie(
        s, [1.0 + 0.001 * i for i in range(60)], termina_ha_min=120
    )  # termina ha 2 h, 5h de dados
    _serie(s, [2.0 + 0.001 * i for i in range(12)])  # volta nos ultimos 60 min
    e = _estacao(client)
    assert e["lacunas_7d"] == 1
    assert 60 <= e["maior_lacuna_min"] <= 70
    assert e["cobertura_24h_pct"] < 40


def test_sensor_com_valor_identico_por_horas_e_marcado_como_travado(
    client: TestClient, s: Session
) -> None:
    semear(s)
    s.commit()
    _serie(s, [1.77] * 80)  # ~6,6 h sem variar
    assert _estacao(client)["possivelmente_travado"] is True


def test_fonte_com_falhas_seguidas_fica_instavel(client: TestClient, s: Session) -> None:
    semear(s)
    s.commit()
    fonte = s.scalars(select(Fonte).where(Fonte.codigo == "dcsc_graphql")).one()
    s.add(
        LogColeta(
            fonte_id=fonte.id,
            executado_em=AGORA - timedelta(minutes=30),
            duracao_ms=1,
            registros=5,
            status=StatusColeta.SUCESSO.value,
        )
    )
    for k in range(3):
        s.add(
            LogColeta(
                fonte_id=fonte.id,
                executado_em=AGORA - timedelta(minutes=20 - k * 5),
                duracao_ms=1,
                registros=0,
                status=StatusColeta.FALHA.value,
                mensagem="timeout",
            )
        )
    s.commit()
    f = next(
        x for x in client.get("/api/qualidade").json()["fontes"] if x["codigo"] == "dcsc_graphql"
    )
    assert f["falhas_seguidas"] == 3 and f["instavel"] is True
    assert f["ultimo_sucesso"] is not None and f["ultima_mensagem"] == "timeout"


def test_uma_falha_isolada_nao_torna_a_fonte_instavel(client: TestClient, s: Session) -> None:
    semear(s)
    s.commit()
    fonte = s.scalars(select(Fonte).where(Fonte.codigo == "dcsc_graphql")).one()
    s.add(
        LogColeta(
            fonte_id=fonte.id,
            executado_em=AGORA - timedelta(minutes=10),
            duracao_ms=1,
            registros=0,
            status="falha",
            mensagem="x",
        )
    )
    s.add(
        LogColeta(
            fonte_id=fonte.id,
            executado_em=AGORA - timedelta(minutes=5),
            duracao_ms=1,
            registros=9,
            status="sucesso",
        )
    )
    s.commit()
    f = next(
        x for x in client.get("/api/qualidade").json()["fontes"] if x["codigo"] == "dcsc_graphql"
    )
    assert f["falhas_seguidas"] == 0 and f["instavel"] is False
