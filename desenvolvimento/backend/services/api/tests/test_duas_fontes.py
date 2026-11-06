"""Mesma medicao vinda de mais de uma fonte (instantes a segundos de distancia): conta uma vez."""

from datetime import UTC, datetime, timedelta

import pytest
from common.enums import Faixa, Variavel
from common.models import Alerta, Estacao, Fonte, Leitura
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import consultas
from api.alertas import LEITURAS_PARA_DESCER, avaliar_estacao
from api.consultas import ultima_leitura, ultimas_leituras

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
LIMITE = timedelta(minutes=30)


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def _est(s: Session, codigo: str) -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()


def grava(
    s: Session,
    codigo: str,
    fonte: str,
    pontos: list[tuple[timedelta, float]],
    variavel: str = "nivel_m",
    qualidade: str = "ok",
) -> None:
    """`pontos`: (tempo antes de AGORA, valor)."""
    est = _est(s, codigo)
    f = s.scalars(select(Fonte).where(Fonte.codigo == fonte)).one()
    for antes, v in pontos:
        s.add(
            Leitura(
                estacao_id=est.id,
                variavel=variavel,
                valor=v,
                unidade="m",
                medido_em=AGORA - antes,
                fonte_id=f.id,
                qualidade=qualidade,
            )
        )
    s.commit()


def min_(n: float, seg: float = 0) -> timedelta:
    return timedelta(minutes=n, seconds=seg)


def duas_fontes(
    s: Session, codigo: str, niveis: list[float], com_rest: bool = False, primeiro: int = 0
) -> None:
    """Um nivel por instante de 5 em 5 min (do mais novo para o mais antigo); GraphQL e painel
    gravam o mesmo instante com segundos de diferenca (e a REST, se pedido)."""
    for i, v in enumerate(niveis, start=primeiro):
        grava(s, codigo, "dcsc_graphql", [(min_(5 * i, 2), v)])
        grava(s, codigo, "pdc_municipal", [(min_(5 * i, 9), v)])
        if com_rest:
            grava(s, codigo, "dcsc_rest", [(min_(5 * i), v)])


# ---------- consultas ----------


def test_ultimas_leituras_devolve_instantes_distintos_nao_uma_por_fonte(base: Session) -> None:
    duas_fontes(base, "DCSC-00043", [1.0, 1.1, 1.2, 1.3])
    r = ultimas_leituras(base, _est(base, "DCSC-00043").id, Variavel.NIVEL_M, 3)
    assert [v for _, v in r] == [1.0, 1.1, 1.2]
    assert len({t for t, _ in r}) == 3
    assert all(r[i][0] - r[i + 1][0] >= timedelta(minutes=4) for i in range(2))


def test_tres_fontes_no_mesmo_instante_contam_uma_vez(base: Session) -> None:
    duas_fontes(base, "DCSC-00043", [1.0, 1.1, 1.2], com_rest=True)
    r = ultimas_leituras(base, _est(base, "DCSC-00043").id, Variavel.NIVEL_M, 5)
    assert [v for _, v in r] == [1.0, 1.1, 1.2]


def test_leituras_separadas_pela_fronteira_de_5_min_continuam_um_so_instante(base: Session) -> None:
    # 11:59:58 (REST) e 12:00:02 (painel) caem em baldes de date_bin diferentes: ainda e uma medicao
    grava(base, "DCSC-00043", "dcsc_rest", [(timedelta(seconds=2), 2.0)])
    grava(base, "DCSC-00043", "pdc_municipal", [(timedelta(seconds=-2), 2.0)])
    r = ultimas_leituras(base, _est(base, "DCSC-00043").id, Variavel.NIVEL_M, 5)
    assert len(r) == 1


def test_escolha_da_fonte_e_deterministica_pela_prioridade(base: Session) -> None:
    grava(base, "DCSC-00043", "dcsc_rest", [(min_(0, 1), 1.01)])
    grava(base, "DCSC-00043", "pdc_municipal", [(min_(0, 5), 1.02)])
    grava(base, "DCSC-00043", "dcsc_graphql", [(min_(0, 9), 1.03)])
    leitura, fonte = ultima_leitura(base, _est(base, "DCSC-00043").id, Variavel.NIVEL_M) or (0, 0)
    assert fonte == "dcsc_graphql" and leitura.valor == 1.03  # type: ignore[union-attr]
    # sem o GraphQL, o painel municipal vence a REST
    grava(base, "DCSC-00174", "dcsc_rest", [(min_(0, 1), 2.01)])
    grava(base, "DCSC-00174", "pdc_municipal", [(min_(0, 5), 2.02)])
    assert ultima_leitura(base, _est(base, "DCSC-00174").id, Variavel.NIVEL_M)[1] == "pdc_municipal"  # type: ignore[index]


def test_mesma_fonte_com_leituras_proximas_nao_e_fundida(base: Session) -> None:
    grava(base, "DCSC-00043", "dcsc_graphql", [(min_(0), 1.0), (min_(1), 1.1), (min_(2), 1.2)])
    assert len(ultimas_leituras(base, _est(base, "DCSC-00043").id, Variavel.NIVEL_M, 5)) == 3


def test_so_leituras_ok_entram(base: Session) -> None:
    grava(base, "DCSC-00043", "dcsc_graphql", [(min_(0), 9.0)], qualidade="suspeita")
    grava(base, "DCSC-00043", "pdc_municipal", [(min_(0, 5), 9.0)], qualidade="descartada")
    grava(base, "DCSC-00043", "dcsc_rest", [(min_(10), 1.5)])
    est = _est(base, "DCSC-00043").id
    assert [v for _, v in ultimas_leituras(base, est, Variavel.NIVEL_M, 3)] == [1.5]


def test_serie_recente_sem_duplicatas_e_em_ordem_cronologica(base: Session) -> None:
    duas_fontes(base, "DCSC-00043", [1.4, 1.3, 1.2, 1.1, 1.0], com_rest=True)
    est = _est(base, "DCSC-00043").id
    s = consultas.serie_recente(base, est, Variavel.NIVEL_M, AGORA, 150)
    assert [v for _, v in s] == [1.0, 1.1, 1.2, 1.3, 1.4]
    assert [t for t, _ in s] == sorted(t for t, _ in s)
    assert len({t for t, _ in s}) == len(s)


def test_endpoint_atual_calcula_a_taxa_sobre_a_serie_sem_duplicar(
    client: TestClient, base: Session
) -> None:
    # sobe 10 cm por hora, medido por duas fontes: a taxa nao pode dobrar nem zerar
    for i in range(0, 130, 5):
        v = 1.0 - 0.1 * i / 60
        grava(base, "DCSC-00043", "dcsc_graphql", [(min_(i, 2), v)])
        grava(base, "DCSC-00043", "pdc_municipal", [(min_(i, 9), v)])
    r = client.get("/api/estacoes/DCSC-00043/atual").json()
    assert r["fonte"] == "dcsc_graphql"
    assert r["taxa_cm_h"] == pytest.approx(10.0, abs=0.5)


# ---------- histerese (RN10) ----------


def _abre_alerta(s: Session, codigo: str, faixa: Faixa) -> None:
    s.add(
        Alerta(
            estacao_id=_est(s, codigo).id,
            faixa_anterior="normal",
            faixa_nova=faixa.value,
            severidade=faixa.value,
            origem="observado",
            criado_em=AGORA - timedelta(hours=3),
        )
    )
    s.commit()


def test_histerese_com_duas_fontes_exige_tres_instantes_distintos(base: Session) -> None:
    assert LEITURAS_PARA_DESCER == 3
    _abre_alerta(base, "DCSC-00174", Faixa.ALERTA)  # Revolver: alerta a partir de 3,00 m
    est = _est(base, "DCSC-00174")
    duas_fontes(base, est.codigo, [2.0, 2.0])  # 4 linhas, mas so 2 instantes
    assert avaliar_estacao(base, est, AGORA, LIMITE) is None
    duas_fontes(base, est.codigo, [2.0], primeiro=2)  # o terceiro instante
    r = avaliar_estacao(base, est, AGORA, LIMITE)
    assert r is not None and r[0].tipo == "desce" and r[0].para == Faixa.NORMAL
