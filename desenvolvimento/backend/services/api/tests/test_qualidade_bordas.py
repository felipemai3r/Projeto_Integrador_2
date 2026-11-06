"""Qualidade dos dados: limites de travado, lacuna, falhas seguidas e estacoes sem nivel."""

from datetime import UTC, datetime, timedelta

import pytest
from common.models import Estacao, Fonte, Leitura, LogColeta
from common.seed import semear
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.qualidade import (
    FALHAS_PARA_INSTAVEL,
    LACUNA_MIN,
    TRAVADO_HORAS,
    qualidade_das_estacoes,
    qualidade_das_fontes,
)

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def grava(
    s: Session,
    estacao: str,
    variavel: str,
    pontos: list[tuple[datetime, float]],
    qualidade: str = "ok",
    fonte: str = "dcsc_rest",
) -> None:
    est = s.scalars(select(Estacao).where(Estacao.codigo == estacao)).one()
    f = s.scalars(select(Fonte).where(Fonte.codigo == fonte)).one()
    for t, v in pontos:
        s.add(
            Leitura(
                estacao_id=est.id,
                variavel=variavel,
                valor=v,
                unidade="m",
                medido_em=t,
                fonte_id=f.id,
                qualidade=qualidade,
            )
        )
    s.commit()


def recentes(
    n: int, valor: float | None = None, passo_min: int = 1
) -> list[tuple[datetime, float]]:
    """`n` leituras terminando em AGORA. Sem `valor`, os valores variam."""
    return [
        (
            AGORA - timedelta(minutes=passo_min * (n - 1 - i)),
            valor if valor is not None else i * 0.01,
        )
        for i in range(n)
    ]


def linha(s: Session, estacao: str, variavel: str = "nivel_m"):
    todas = qualidade_das_estacoes(s, AGORA)
    return next((e for e in todas if e.estacao == estacao and e.variavel == variavel), None)


# ---------- travado ----------


def test_constantes_documentadas() -> None:
    assert (FALHAS_PARA_INSTAVEL, LACUNA_MIN, TRAVADO_HORAS) == (3, 15, 6)


def test_sensor_travado_exige_ao_menos_60_leituras_iguais_nas_ultimas_6h(base: Session) -> None:
    grava(base, "DCSC-00043", "nivel_m", recentes(59, valor=1.77))
    assert linha(base, "DCSC-00043").possivelmente_travado is False
    grava(base, "DCSC-00043", "nivel_m", [(AGORA - timedelta(minutes=70), 1.77)])
    assert linha(base, "DCSC-00043").possivelmente_travado is True  # 60 leituras iguais


def test_um_unico_valor_diferente_destrava(base: Session) -> None:
    pontos = recentes(80, valor=1.77)
    pontos[40] = (pontos[40][0], 1.78)
    grava(base, "DCSC-00043", "nivel_m", pontos)
    assert linha(base, "DCSC-00043").possivelmente_travado is False


def test_leituras_iguais_mais_antigas_que_6h_nao_travam(base: Session) -> None:
    antigas = [(AGORA - timedelta(hours=7, minutes=m), 1.77) for m in range(80)]
    grava(base, "DCSC-00043", "nivel_m", antigas + [(AGORA, 2.5)])
    assert linha(base, "DCSC-00043").possivelmente_travado is False


def test_leituras_suspeitas_iguais_nao_contam_para_travado(base: Session) -> None:
    grava(base, "DCSC-00043", "nivel_m", recentes(80, valor=1.77), qualidade="suspeita")
    assert linha(base, "DCSC-00043").possivelmente_travado is False


def test_chuva_acumulada_com_valor_repetido_nao_e_sensor_travado(base: Session) -> None:
    grava(base, "DCSC-00043", "chuva_acumulada_mm", recentes(80, valor=0.0), fonte="dcsc_rest")
    assert linha(base, "DCSC-00043", "chuva_acumulada_mm").possivelmente_travado is False


# ---------- cobertura e lacunas ----------


def test_cobertura_nunca_passa_de_100_por_cento(base: Session) -> None:
    # leituras a cada minuto por 24 h: muito mais que 288 leituras, mas so 288 baldes de 5 min
    grava(base, "DCSC-00043", "nivel_m", recentes(24 * 60, passo_min=1))
    assert linha(base, "DCSC-00043").cobertura_24h_pct == 100.0


def test_cobertura_conta_baldes_de_5_min_e_nao_leituras(base: Session) -> None:
    # 12 leituras dentro do mesmo balde de 5 minutos valem 1 balde: 1/288
    inicio = datetime(2026, 11, 5, 11, 0, tzinfo=UTC)
    grava(
        base,
        "DCSC-00043",
        "nivel_m",
        [(inicio + timedelta(seconds=10 * i), 1.0 + i) for i in range(12)],
    )
    assert linha(base, "DCSC-00043").cobertura_24h_pct == pytest.approx(0.3, abs=0.05)


def test_lacuna_so_conta_quando_passa_de_15_minutos(base: Session) -> None:
    t = AGORA - timedelta(hours=2)
    pontos = [(t, 1.0), (t + timedelta(minutes=15), 1.1), (t + timedelta(minutes=15 + 16), 1.2)]
    grava(base, "DCSC-00043", "nivel_m", pontos)
    e = linha(base, "DCSC-00043")
    assert e.lacunas_7d == 1 and e.maior_lacuna_min == 16


def test_serie_continua_a_cada_5_minutos_nao_tem_lacuna(base: Session) -> None:
    grava(base, "DCSC-00043", "nivel_m", recentes(100, passo_min=5))
    e = linha(base, "DCSC-00043")
    assert e.lacunas_7d == 0 and e.maior_lacuna_min == 5


def test_leitura_de_fontes_diferentes_no_mesmo_instante_nao_cria_passo_zero(base: Session) -> None:
    """Revolver tem nivel do GraphQL e do painel: instantes repetidos contam uma vez."""
    pontos = recentes(20, passo_min=5)
    grava(base, "DCSC-00174", "nivel_m", pontos, fonte="dcsc_graphql")
    grava(base, "DCSC-00174", "nivel_m", pontos, fonte="pdc_municipal")
    e = linha(base, "DCSC-00174")
    assert e.lacunas_7d == 0 and e.maior_lacuna_min == 5


def test_descartadas_e_suspeitas_sao_contadas_por_variavel_nos_ultimos_7_dias(
    base: Session,
) -> None:
    grava(base, "DCSC-00043", "nivel_m", recentes(5, passo_min=5))
    grava(
        base,
        "DCSC-00043",
        "nivel_m",
        [(AGORA - timedelta(minutes=31), 99.0)],
        qualidade="descartada",
    )
    grava(
        base,
        "DCSC-00043",
        "nivel_m",
        [(AGORA - timedelta(minutes=32 + i), 9.0) for i in range(3)],
        qualidade="suspeita",
    )
    grava(
        base, "DCSC-00043", "nivel_m", [(AGORA - timedelta(days=8), 99.0)], qualidade="descartada"
    )
    e = linha(base, "DCSC-00043")
    assert (e.descartadas_7d, e.suspeitas_7d) == (1, 3)  # a de 8 dias atras nao entra


# ---------- quais estacoes aparecem ----------


def test_estacao_sem_nenhuma_leitura_de_serie_nao_aparece(base: Session) -> None:
    assert qualidade_das_estacoes(base, AGORA) == []


def test_estacao_inativa_nao_aparece(base: Session) -> None:
    grava(base, "DCSC-00043", "nivel_m", recentes(5))
    base.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one().ativa = False
    base.commit()
    assert qualidade_das_estacoes(base, AGORA) == []


def test_estacao_com_nivel_e_chuva_gera_uma_linha_por_variavel_ordenadas_por_codigo(
    base: Session,
) -> None:
    grava(base, "DCSC-00043", "nivel_m", recentes(5))
    grava(base, "DCSC-00043", "chuva_acumulada_mm", recentes(5))
    grava(base, "DCSC-00037", "chuva_acumulada_mm", recentes(5))
    todas = qualidade_das_estacoes(base, AGORA)
    assert [(e.estacao, e.variavel) for e in todas] == [
        ("DCSC-00037", "chuva_acumulada_mm"),
        ("DCSC-00043", "nivel_m"),
        ("DCSC-00043", "chuva_acumulada_mm"),
    ]


def test_ultima_leitura_considera_qualquer_qualidade(base: Session) -> None:
    grava(base, "DCSC-00043", "nivel_m", [(AGORA - timedelta(hours=1), 1.0)])
    grava(
        base, "DCSC-00043", "nivel_m", [(AGORA - timedelta(minutes=10), 99.0)], qualidade="suspeita"
    )
    assert linha(base, "DCSC-00043").ultima_leitura == AGORA - timedelta(minutes=10)


# ---------- fontes ----------


def log(s: Session, fonte: str, minutos_atras: int, status: str, msg: str | None = None) -> None:
    f = s.scalars(select(Fonte).where(Fonte.codigo == fonte)).one()
    s.add(
        LogColeta(
            fonte_id=f.id,
            executado_em=AGORA - timedelta(minutes=minutos_atras),
            duracao_ms=1,
            registros=0,
            status=status,
            mensagem=msg,
        )
    )
    s.commit()


def fonte(s: Session, codigo: str):
    return next(f for f in qualidade_das_fontes(s) if f.codigo == codigo)


def test_fonte_sem_nenhum_log_nao_e_instavel_e_nao_tem_datas(base: Session) -> None:
    f = fonte(base, "pdc_municipal")
    assert (f.ultima_coleta, f.ultimo_sucesso, f.status_ultima) == (None, None, None)
    assert f.falhas_seguidas == 0 and f.instavel is False and f.ultima_mensagem is None


def test_tres_falhas_seguidas_tornam_instavel_e_duas_nao(base: Session) -> None:
    log(base, "pdc_municipal", 30, "sucesso")
    log(base, "pdc_municipal", 20, "falha", "a")
    log(base, "pdc_municipal", 10, "falha", "b")
    assert fonte(base, "pdc_municipal").instavel is False
    log(base, "pdc_municipal", 5, "falha", "c")
    f = fonte(base, "pdc_municipal")
    assert (f.falhas_seguidas, f.instavel, f.ultima_mensagem) == (3, True, "c")
    assert f.ultimo_sucesso == AGORA - timedelta(minutes=30)


def test_coleta_vazia_conta_como_nao_falha_e_zera_a_sequencia(base: Session) -> None:
    for m, st in [(40, "falha"), (30, "falha"), (20, "falha"), (10, "vazio")]:
        log(base, "pdc_municipal", m, st, "x")
    f = fonte(base, "pdc_municipal")
    assert f.falhas_seguidas == 0 and f.instavel is False
    assert f.ultimo_sucesso == AGORA - timedelta(minutes=10) and f.ultima_mensagem is None


def test_so_falhas_deixam_ultimo_sucesso_vazio_e_instavel(base: Session) -> None:
    for m in (15, 10, 5):
        log(base, "dcsc_rest", m, "falha", "timeout")
    f = fonte(base, "dcsc_rest")
    assert f.ultimo_sucesso is None and f.instavel is True


def test_mensagem_so_aparece_quando_a_ultima_coleta_falhou(base: Session) -> None:
    log(base, "dcsc_rest", 10, "falha", "timeout")
    log(base, "dcsc_rest", 5, "sucesso", "5 lidas")
    assert fonte(base, "dcsc_rest").ultima_mensagem is None


def test_fonte_inativa_nao_e_listada_e_a_lista_vem_ordenada_por_codigo(base: Session) -> None:
    base.scalars(select(Fonte).where(Fonte.codigo == "ana_hidroweb")).one().ativa = False
    base.commit()
    codigos = [f.codigo for f in qualidade_das_fontes(base)]
    assert "ana_hidroweb" not in codigos and codigos == sorted(codigos)
    assert "pdc_municipal" in codigos


def test_so_as_50_coletas_mais_recentes_entram_na_conta_de_falhas(base: Session) -> None:
    for m in range(1, 61):
        log(base, "dcsc_rest", m, "falha", "x")
    assert fonte(base, "dcsc_rest").falhas_seguidas == 50
