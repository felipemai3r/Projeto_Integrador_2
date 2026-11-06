"""Qualidade enxerga as estacoes so de chuva (chuva_h001_mm), mas so com fonte medida."""

from datetime import UTC, datetime, timedelta

import pytest
from common.models import Estacao, Fonte, Leitura
from common.seed import semear
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.qualidade import qualidade_das_estacoes

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def grava(s: Session, codigo: str, variavel: str, fonte: str, n: int, passo_min: int = 5) -> None:
    est = s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()
    f = s.scalars(select(Fonte).where(Fonte.codigo == fonte)).one()
    for i in range(n):
        s.add(
            Leitura(
                estacao_id=est.id,
                variavel=variavel,
                valor=0.1 * i,
                unidade="mm",
                medido_em=AGORA - timedelta(minutes=passo_min * i),
                fonte_id=f.id,
                qualidade="ok",
            )
        )
    s.commit()


def linhas(s: Session, codigo: str) -> dict[str, object]:
    return {e.variavel: e for e in qualidade_das_estacoes(s, AGORA) if e.estacao == codigo}


def test_estacao_so_de_chuva_do_painel_aparece_com_cobertura(base: Session) -> None:
    grava(base, "DC-PEU-002", "chuva_h001_mm", "pdc_municipal", 144)  # 12 h a cada 5 min
    e = linhas(base, "DC-PEU-002")["chuva_h001_mm"]
    assert e.cobertura_24h_pct == 50.0  # type: ignore[attr-defined]
    assert e.possivelmente_travado is False  # type: ignore[attr-defined]
    assert set(linhas(base, "DC-PEU-002")) == {"chuva_h001_mm"}


def test_reanalise_era5_nao_cria_linha_nem_infla_a_cobertura(base: Session) -> None:
    grava(base, "DC-PEU-003", "chuva_h001_mm", "openmeteo_archive", 24, passo_min=60)
    assert linhas(base, "DC-PEU-003") == {}
    grava(base, "DC-PEU-003", "chuva_h001_mm", "pdc_municipal", 12)
    e = linhas(base, "DC-PEU-003")["chuva_h001_mm"]
    assert e.cobertura_24h_pct == pytest.approx(4.2, abs=0.05)  # type: ignore[attr-defined]
    assert e.ultima_leitura == AGORA  # type: ignore[attr-defined]


def test_estacao_com_graphql_ganha_a_linha_de_h001_alem_da_de_nivel(base: Session) -> None:
    grava(base, "DCSC-00043", "nivel_m", "dcsc_graphql", 10)
    grava(base, "DCSC-00043", "chuva_h001_mm", "dcsc_graphql", 10)
    assert set(linhas(base, "DCSC-00043")) == {"nivel_m", "chuva_h001_mm"}


def test_sensor_de_nivel_travado_com_duas_fontes_exige_a_cobertura_de_uma(base: Session) -> None:
    # 40 instantes iguais gravados por duas fontes = 80 linhas: nao pode virar "travado"
    for fonte in ("dcsc_graphql", "pdc_municipal"):
        est = base.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one()
        f = base.scalars(select(Fonte).where(Fonte.codigo == fonte)).one()
        deslocamento = 3 if fonte == "pdc_municipal" else 0
        for i in range(40):
            base.add(
                Leitura(
                    estacao_id=est.id,
                    variavel="nivel_m",
                    valor=1.77,
                    unidade="m",
                    medido_em=AGORA - timedelta(minutes=5 * i, seconds=deslocamento),
                    fonte_id=f.id,
                    qualidade="ok",
                )
            )
    base.commit()
    assert linhas(base, "DCSC-00043")["nivel_m"].possivelmente_travado is False  # type: ignore[attr-defined]
