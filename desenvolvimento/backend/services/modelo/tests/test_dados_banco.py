"""Leitura de series do banco real de teste: filtros de qualidade, de fonte e de janela.

Cobre `_serie_bruta`, `nivel_horario` e `chuva_horaria` (fallback h001) contra o PostgreSQL.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from common.models import Estacao, Fonte, Leitura
from common.seed import semear
from sqlalchemy import select
from sqlalchemy.orm import Session

from modelo.dados import chuva_horaria, nivel_horario

T0 = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
PG = "DCSC-00043"
SERRA = "DC-PEU-003"


@pytest.fixture
def banco(s: Session) -> Session:
    semear(s)
    s.add(Fonte(codigo="fonte_x", nome="X", base_url="x", frequencia_s=300))
    s.commit()
    return s


def grava(
    s: Session,
    estacao: str,
    variavel: str,
    pares: list[tuple[datetime, float | None]],
    fonte: str = "pdc_municipal",
    qualidade: str = "ok",
) -> None:
    est = s.scalars(select(Estacao).where(Estacao.codigo == estacao)).one()
    f = s.scalars(select(Fonte).where(Fonte.codigo == fonte)).one()
    for t, v in pares:
        s.add(
            Leitura(
                estacao_id=est.id,
                variavel=variavel,
                valor=v,
                unidade="x",
                medido_em=t,
                fonte_id=f.id,
                qualidade=qualidade,
            )
        )
    s.commit()


def cada_5min(inicio: datetime, n: int, valor: float) -> list[tuple[datetime, float]]:
    return [(inicio + timedelta(minutes=5 * i), valor) for i in range(n)]


# ---------- nivel ----------


def test_nivel_exige_seis_leituras_na_hora_e_usa_a_media(banco: Session) -> None:
    grava(banco, PG, "nivel_m", cada_5min(T0, 5, 2.0))  # hora 00: 5 leituras -> NaN
    grava(banco, PG, "nivel_m", cada_5min(T0 + timedelta(hours=1), 6, 3.0))  # hora 01: 6 -> media
    serie = nivel_horario(banco, PG, T0, T0 + timedelta(hours=3))
    assert np.isnan(serie[pd.Timestamp(T0)])
    assert serie[pd.Timestamp(T0 + timedelta(hours=1))] == pytest.approx(3.0)


def test_nivel_ignora_leitura_suspeita_e_descartada(banco: Session) -> None:
    grava(banco, PG, "nivel_m", cada_5min(T0, 6, 2.0))
    grava(banco, PG, "nivel_m", [(T0 + timedelta(minutes=1), 50.0)], qualidade="suspeita")
    grava(banco, PG, "nivel_m", [(T0 + timedelta(minutes=2), -9.0)], qualidade="descartada")
    serie = nivel_horario(banco, PG, T0, T0 + timedelta(hours=2))
    assert serie.iloc[0] == pytest.approx(2.0)


def test_nivel_ignora_valor_nulo(banco: Session) -> None:
    grava(banco, PG, "nivel_m", cada_5min(T0, 5, 2.0) + [(T0 + timedelta(minutes=25), None)])
    assert np.isnan(nivel_horario(banco, PG, T0, T0 + timedelta(hours=2)).iloc[0])  # so 5 validas


def test_nivel_fim_da_janela_e_exclusivo_e_inicio_inclusivo(banco: Session) -> None:
    grava(banco, PG, "nivel_m", cada_5min(T0, 12, 1.0))  # hora 00 completa
    grava(banco, PG, "nivel_m", cada_5min(T0 + timedelta(hours=1), 12, 9.0))  # hora 01
    so_primeira = nivel_horario(banco, PG, T0, T0 + timedelta(hours=1))
    assert list(so_primeira.index) == [pd.Timestamp(T0)] and so_primeira.iloc[0] == 1.0
    so_segunda = nivel_horario(banco, PG, T0 + timedelta(hours=1), T0 + timedelta(hours=2))
    assert so_segunda.iloc[0] == 9.0


def test_nivel_de_outra_estacao_ou_variavel_nao_entra(banco: Session) -> None:
    grava(banco, "DCSC-00174", "nivel_m", cada_5min(T0, 12, 7.0))
    grava(banco, PG, "reservatorio_m", cada_5min(T0, 12, 8.0))
    assert nivel_horario(banco, PG, T0, T0 + timedelta(hours=2)).empty


def test_nivel_sem_leitura_devolve_serie_vazia_com_indice_de_tempo(banco: Session) -> None:
    serie = nivel_horario(banco, PG, T0, T0 + timedelta(hours=2))
    assert serie.empty and isinstance(serie.index, pd.DatetimeIndex)


def test_nivel_duas_fontes_na_mesma_estacao_fazem_media_nao_soma(banco: Session) -> None:
    """Creche (DCSC-00174): nivel vem do GraphQL e do painel municipal, quase iguais."""
    grava(banco, "DCSC-00174", "nivel_m", cada_5min(T0, 12, 1.00), fonte="dcsc_graphql")
    grava(
        banco,
        "DCSC-00174",
        "nivel_m",
        cada_5min(T0 + timedelta(seconds=40), 12, 1.10),
        fonte="pdc_municipal",
    )
    serie = nivel_horario(banco, "DCSC-00174", T0, T0 + timedelta(hours=1))
    assert serie.iloc[0] == pytest.approx(1.05)


def test_nivel_tres_instantes_em_duas_fontes_continuam_sem_cobertura(banco: Session) -> None:
    """GraphQL e painel gravam o mesmo nivel com segundos de diferenca: 3 instantes, nao 6."""
    grava(banco, PG, "nivel_m", cada_5min(T0, 3, 2.0), fonte="dcsc_graphql")
    grava(
        banco, PG, "nivel_m", cada_5min(T0 + timedelta(seconds=40), 3, 2.0), fonte="pdc_municipal"
    )
    assert np.isnan(nivel_horario(banco, PG, T0, T0 + timedelta(hours=1)).iloc[0])
    # com 6 instantes distintos passa, e a media segue sendo a do nivel
    grava(banco, PG, "nivel_m", cada_5min(T0 + timedelta(minutes=15), 3, 2.0), fonte="dcsc_rest")
    assert nivel_horario(banco, PG, T0, T0 + timedelta(hours=1)).iloc[0] == pytest.approx(2.0)


def test_chuva_incremento_de_duas_fontes_nao_soma_duas_vezes(banco: Session) -> None:
    grava(banco, PG, "chuva_acumulada_mm", cada_5min(T0, 10, 0.5), fonte="dcsc_rest")
    grava(
        banco,
        PG,
        "chuva_acumulada_mm",
        cada_5min(T0 + timedelta(seconds=30), 10, 0.5),
        fonte="dcsc_graphql",
    )
    assert chuva_horaria(banco, PG, T0, T0 + timedelta(hours=1)).iloc[0] == pytest.approx(5.0)


# ---------- chuva: fallback h001 e lista branca de fontes ----------


def test_h001_so_de_fonte_medida_conta_e_reanalise_e_ignorada(banco: Session) -> None:
    fecha = T0 + timedelta(hours=1)
    grava(banco, SERRA, "chuva_h001_mm", [(fecha, 4.0)], fonte="pdc_municipal")
    grava(banco, SERRA, "chuva_h001_mm", [(fecha, 99.0)], fonte="openmeteo_archive")
    grava(banco, SERRA, "chuva_h001_mm", [(fecha, 77.0)], fonte="openmeteo_forecast")
    grava(banco, SERRA, "chuva_h001_mm", [(fecha, 55.0)], fonte="fonte_x")
    serie = chuva_horaria(banco, SERRA, T0, T0 + timedelta(hours=1))
    assert serie.to_dict() == {pd.Timestamp(T0): 4.0}


def test_estacao_so_com_reanalise_fica_sem_chuva_em_vez_de_usar_modelo(banco: Session) -> None:
    grava(
        banco,
        SERRA,
        "chuva_h001_mm",
        [(T0 + timedelta(hours=h), 5.0) for h in range(1, 5)],
        fonte="openmeteo_archive",
    )
    assert chuva_horaria(banco, SERRA, T0, T0 + timedelta(hours=4)).empty


@pytest.mark.parametrize("fonte", ["dcsc_graphql", "dcsc_rest", "pdc_municipal"])
def test_cada_fonte_medida_da_lista_branca_alimenta_o_h001(banco: Session, fonte: str) -> None:
    grava(banco, SERRA, "chuva_h001_mm", [(T0 + timedelta(hours=1), 2.5)], fonte=fonte)
    assert chuva_horaria(banco, SERRA, T0, T0 + timedelta(hours=1)).iloc[0] == 2.5


def test_h001_suspeito_nao_entra(banco: Session) -> None:
    grava(banco, SERRA, "chuva_h001_mm", [(T0 + timedelta(hours=1), 248.28)], qualidade="suspeita")
    assert chuva_horaria(banco, SERRA, T0, T0 + timedelta(hours=1)).empty


def test_tolerancia_do_h001_no_banco_cinco_min_antes_e_um_min_depois(banco: Session) -> None:
    fecha = T0 + timedelta(hours=1)
    grava(banco, SERRA, "chuva_h001_mm", [(fecha - timedelta(minutes=5), 1.0)])  # 00:55 -> hora 00
    grava(banco, PG, "chuva_h001_mm", [(fecha + timedelta(minutes=1), 2.0)])  # 01:01 -> hora 00
    grava(banco, "DCSC-00037", "chuva_h001_mm", [(fecha + timedelta(minutes=2), 3.0)])  # fora
    grava(banco, "DCSC-00015", "chuva_h001_mm", [(fecha - timedelta(minutes=6), 4.0)])  # fora
    fim = T0 + timedelta(hours=1)
    assert chuva_horaria(banco, SERRA, T0, fim).iloc[0] == 1.0
    assert chuva_horaria(banco, PG, T0, fim).iloc[0] == 2.0
    assert chuva_horaria(banco, "DCSC-00037", T0, fim).empty
    assert chuva_horaria(banco, "DCSC-00015", T0, fim).empty


def test_leitura_h001_exatamente_no_fim_da_janela_fecha_a_ultima_hora(banco: Session) -> None:
    """A hora [fim-1h, fim) so e conhecida pela leitura de `fim`, que o filtro `< fim` cortaria."""
    fim = T0 + timedelta(hours=3)
    grava(banco, SERRA, "chuva_h001_mm", [(fim, 6.0)])
    serie = chuva_horaria(banco, SERRA, T0, fim)
    assert serie.to_dict() == {pd.Timestamp(T0 + timedelta(hours=2)): 6.0}


def test_incremento_com_cobertura_vence_o_h001_no_banco(banco: Session) -> None:
    grava(banco, PG, "chuva_acumulada_mm", cada_5min(T0, 12, 0.5), fonte="dcsc_rest")  # 6 mm
    grava(banco, PG, "chuva_h001_mm", [(T0 + timedelta(hours=1), 40.0)], fonte="dcsc_graphql")
    assert chuva_horaria(banco, PG, T0, T0 + timedelta(hours=1)).iloc[0] == pytest.approx(6.0)


def test_incremento_com_cobertura_baixa_no_banco_cai_no_h001(banco: Session) -> None:
    grava(banco, PG, "chuva_acumulada_mm", cada_5min(T0, 8, 0.5), fonte="dcsc_rest")  # 8 < 9
    grava(banco, PG, "chuva_h001_mm", [(T0 + timedelta(hours=1), 3.0)], fonte="dcsc_graphql")
    assert chuva_horaria(banco, PG, T0, T0 + timedelta(hours=1)).iloc[0] == 3.0


def test_duas_fontes_medidas_na_mesma_hora_dao_uma_leitura_so(banco: Session) -> None:
    """DCSC-00043 vem do GraphQL e do painel municipal: 4,0 e 4,2 viram ~4,1, nunca 8,2."""
    fecha = T0 + timedelta(hours=1)
    grava(banco, PG, "chuva_h001_mm", [(fecha, 4.0)], fonte="dcsc_graphql")
    grava(banco, PG, "chuva_h001_mm", [(fecha + timedelta(seconds=40), 4.2)], fonte="pdc_municipal")
    valor = chuva_horaria(banco, PG, T0, T0 + timedelta(hours=1)).iloc[0]
    assert valor == pytest.approx(4.2)  # a mais tardia dentro da tolerancia, sem somar
    assert valor < 5


def test_pico_espurio_do_painel_nao_vira_chuva_da_hora(banco: Session) -> None:
    """90 mm isolado as 01:00 entre leituras de 0,2 mm (abaixo do teto, mas impossivel em 5 min)."""
    serie = [(t, 90.0 if t == T0 + timedelta(hours=1) else v) for t, v in cada_5min(T0, 14, 0.2)]
    grava(banco, PG, "chuva_h001_mm", serie)
    valor = chuva_horaria(banco, PG, T0, T0 + timedelta(hours=2)).iloc[0]
    assert valor == pytest.approx(0.2)  # cai na leitura das 00:55


def test_leitura_acima_do_teto_de_150_mm_nao_vira_chuva_da_hora_mesmo_marcada_ok(
    banco: Session,
) -> None:
    grava(banco, PG, "chuva_h001_mm", [(T0 + timedelta(hours=1), 248.28)])
    assert chuva_horaria(banco, PG, T0, T0 + timedelta(hours=1)).empty
