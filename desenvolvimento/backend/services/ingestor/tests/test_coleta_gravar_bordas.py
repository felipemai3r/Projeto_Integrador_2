"""Execucao de coleta com log de auditoria e gravacao com mais de uma fonte por estacao."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from common.enums import StatusColeta, Variavel
from common.models import Estacao, Fonte, Leitura, LogColeta
from common.schemas import LeituraBruta
from common.seed import semear
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ingestor.coleta import executar
from ingestor.erros import ContratoQuebrado, FonteIndisponivel
from ingestor.gravar import gravar, registrar_log

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def leitura(
    codigo: str = "DCSC-00174",
    valor: float | None = 1.0,
    minutos: int = 0,
    variavel: Variavel = Variavel.NIVEL_M,
) -> LeituraBruta:
    return LeituraBruta(
        estacao_codigo=codigo,
        variavel=variavel,
        valor=valor,
        unidade="m",
        medido_em=AGORA + timedelta(minutes=minutos),
    )


def ultimo_log(s: Session) -> LogColeta:
    s.expire_all()
    return s.scalars(select(LogColeta).order_by(LogColeta.id.desc())).first()


# ---------- executar ----------


def test_coleta_com_leituras_novas_registra_sucesso_e_a_contagem(base: Session) -> None:
    antigas = datetime.now(UTC) - timedelta(hours=1)
    dados = [
        LeituraBruta(
            estacao_codigo="DCSC-00043",
            variavel=Variavel.NIVEL_M,
            valor=1.5,
            unidade="m",
            medido_em=antigas,
        )
    ]
    assert executar("dcsc_rest", lambda: dados) == StatusColeta.SUCESSO
    lg = ultimo_log(base)
    assert (lg.status, lg.registros) == ("sucesso", 1)
    assert lg.mensagem == "1 lidas, 1 novas, 0 descartadas"
    assert lg.duracao_ms >= 0


def test_coleta_sem_nada_novo_e_vazio_e_nao_falha(base: Session) -> None:
    assert executar("dcsc_rest", lambda: []) == StatusColeta.VAZIO
    lg = ultimo_log(base)
    assert (lg.status, lg.registros) == ("vazio", 0)


def test_fonte_indisponivel_vira_falha_com_o_tipo_na_mensagem_e_nao_propaga(base: Session) -> None:
    def cai() -> list[Any]:
        raise FonteIndisponivel("pdc_municipal: HTTP 503")

    assert executar("pdc_municipal", cai) == StatusColeta.FALHA
    lg = ultimo_log(base)
    assert lg.status == "falha" and lg.registros == 0
    assert lg.mensagem == "FonteIndisponivel: pdc_municipal: HTTP 503"


def test_contrato_quebrado_vira_falha_com_o_tipo_na_mensagem(base: Session) -> None:
    def quebra() -> list[Any]:
        raise ContratoQuebrado("sem lista 'data'")

    assert executar("pdc_municipal", quebra) == StatusColeta.FALHA
    assert ultimo_log(base).mensagem == "ContratoQuebrado: sem lista 'data'"


def test_erro_inesperado_tambem_vira_falha_e_nao_derruba_o_agendador(
    base: Session, caplog: pytest.LogCaptureFixture
) -> None:
    def bug() -> list[Any]:
        raise ZeroDivisionError("x")

    with caplog.at_level(logging.ERROR, logger="ingestor.coleta"):
        assert executar("dcsc_rest", bug) == StatusColeta.FALHA
    assert ultimo_log(base).mensagem.startswith("erro inesperado ZeroDivisionError")
    assert "erro inesperado na coleta" in caplog.text


def test_falha_do_gravador_nao_deixa_leitura_parcial_e_vira_falha(base: Session) -> None:
    def gravador_quebrado(s: Session, fonte: str, leituras: list[Any], agora: datetime):
        s.add(
            Leitura(
                estacao_id=1,
                variavel="nivel_m",
                valor=1.0,
                unidade="m",
                medido_em=AGORA,
                fonte_id=1,
                qualidade="ok",
            )
        )
        s.flush()
        raise RuntimeError("banco caiu no meio")

    assert executar("dcsc_rest", lambda: [leitura()], gravador_quebrado) == StatusColeta.FALHA
    assert base.scalar(select(func.count()).select_from(Leitura)) == 0  # rollback
    assert ultimo_log(base).status == "falha"


def test_o_log_e_gravado_mesmo_quando_a_coleta_falha(base: Session) -> None:
    antes = base.scalar(select(func.count()).select_from(LogColeta))

    def cai() -> list[Any]:
        raise FonteIndisponivel("x")

    executar("dcsc_graphql", cai)
    base.expire_all()
    assert base.scalar(select(func.count()).select_from(LogColeta)) == antes + 1


def test_fonte_sem_cadastro_nao_gera_log_e_nao_quebra(base: Session) -> None:
    assert executar("fonte_que_nao_existe", lambda: []) == StatusColeta.FALHA  # gravar levanta
    assert base.scalar(select(func.count()).select_from(LogColeta)) == 0


def test_registrar_log_corta_mensagem_longa_em_mil_caracteres(base: Session) -> None:
    registrar_log(base, "dcsc_rest", 5, 0, StatusColeta.FALHA, "x" * 5000)
    base.commit()
    assert len(ultimo_log(base).mensagem) == 1000


def test_registrar_log_aceita_mensagem_ausente(base: Session) -> None:
    registrar_log(base, "dcsc_rest", 5, 0, StatusColeta.VAZIO, None)
    base.commit()
    assert ultimo_log(base).mensagem is None


# ---------- gravar com varias fontes na mesma estacao ----------


def test_mesma_leitura_de_duas_fontes_fica_gravada_uma_vez_por_fonte(base: Session) -> None:
    """O Revolver tem nivel no GraphQL e no painel: as duas ficam, o modelo faz a media."""
    gravar(base, "dcsc_graphql", [leitura(valor=1.00)], AGORA)
    gravar(base, "pdc_municipal", [leitura(valor=1.02)], AGORA)
    base.commit()
    fontes = base.scalars(
        select(Fonte.codigo).join(Leitura, Leitura.fonte_id == Fonte.id).order_by(Fonte.codigo)
    ).all()
    assert fontes == ["dcsc_graphql", "pdc_municipal"]


def test_salto_olha_a_leitura_anterior_de_qualquer_fonte(base: Session) -> None:
    gravar(base, "dcsc_graphql", [leitura(valor=1.0, minutos=-5)], AGORA)
    gravar(base, "pdc_municipal", [leitura(valor=2.5, minutos=0)], AGORA)  # +1,5 m em 5 min
    base.commit()
    q = {x.valor: x.qualidade for x in base.scalars(select(Leitura))}
    assert q == {1.0: "ok", 2.5: "suspeita"}


def test_leitura_descartada_de_uma_fonte_nao_serve_de_referencia_para_a_outra(
    base: Session,
) -> None:
    gravar(base, "dcsc_graphql", [leitura(valor=99.0, minutos=-5)], AGORA)  # implausivel
    gravar(base, "pdc_municipal", [leitura(valor=1.0, minutos=0)], AGORA)
    base.commit()
    q = {x.valor: x.qualidade for x in base.scalars(select(Leitura))}
    assert q == {99.0: "descartada", 1.0: "ok"}


def test_estacao_inativa_e_ignorada_na_gravacao(base: Session) -> None:
    base.scalars(select(Estacao).where(Estacao.codigo == "DC-PEU-002")).one().ativa = False
    base.commit()
    dados = [leitura("DC-PEU-002", 0.4, variavel=Variavel.CHUVA_H001_MM)]
    assert gravar(base, "pdc_municipal", dados, AGORA) == (0, 0)


def test_valor_nulo_e_gravado_como_descartado_e_conta_nas_descartadas(base: Session) -> None:
    inseridas, descartadas = gravar(base, "dcsc_rest", [leitura(valor=None)], AGORA)
    base.commit()
    assert (inseridas, descartadas) == (1, 1)
    assert base.scalars(select(Leitura)).one().qualidade == "descartada"


def test_horario_no_futuro_e_gravado_descartado(base: Session) -> None:
    inseridas, descartadas = gravar(base, "dcsc_rest", [leitura(valor=1.0, minutos=30)], AGORA)
    base.commit()
    assert (inseridas, descartadas) == (1, 1)


def test_lista_vazia_nao_grava_nada(base: Session) -> None:
    assert gravar(base, "dcsc_rest", [], AGORA) == (0, 0)


def test_lote_de_mais_de_5000_leituras_e_gravado_inteiro(base: Session) -> None:
    dados = [
        leitura("DCSC-00037", float(i % 7), minutos=-i, variavel=Variavel.CHUVA_H001_MM)
        for i in range(5100)
    ]
    inseridas, _ = gravar(base, "dcsc_graphql", dados, AGORA)
    base.commit()
    assert inseridas == 5100
    assert base.scalar(select(func.count()).select_from(Leitura)) == 5100


def test_leituras_fora_de_ordem_sao_avaliadas_em_ordem_de_tempo(base: Session) -> None:
    """O salto compara com a leitura anterior NO TEMPO, nao a anterior na lista."""
    dados = [
        leitura(valor=2.5, minutos=0),
        leitura(valor=1.0, minutos=-5),
    ]
    gravar(base, "dcsc_rest", dados, AGORA)
    base.commit()
    q = {x.valor: x.qualidade for x in base.scalars(select(Leitura))}
    assert q == {1.0: "ok", 2.5: "suspeita"}
