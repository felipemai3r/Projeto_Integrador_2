"""Seed: consistencia dos cadastros e idempotencia sem sobrescrever o que ja foi editado."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.enums import Faixa, Papel
from common.geo import dentro_do_municipio
from common.models import Estacao, Fonte, Limiar
from common.seed import ESTACOES, ESTACOES_PDC, FONTES, LIMIARES, semear

NOVAS = ("DC-PEU-002", "DC-PEU-003", "DC-PEU-004")


def test_codigos_de_estacao_e_de_fonte_sao_unicos() -> None:
    codigos = [e[0] for e in ESTACOES + ESTACOES_PDC]
    assert len(codigos) == len(set(codigos)) == 11
    fontes = [f[0] for f in FONTES]
    assert len(fontes) == len(set(fontes)) == 7


def test_estacoes_do_painel_ficam_dentro_do_municipio() -> None:
    for codigo, _nome, _curso, lat, lon, _papel in ESTACOES_PDC:
        assert dentro_do_municipio(lat, lon), codigo


def test_estacoes_do_painel_sao_influencia_sem_curso_dagua() -> None:
    assert [e[0] for e in ESTACOES_PDC] == list(NOVAS)
    assert {e[2] for e in ESTACOES_PDC} == {None}
    assert {e[5] for e in ESTACOES_PDC} == {Papel.INFLUENCIA}


def test_so_as_estacoes_com_sensor_de_nivel_e_alvo_tem_limiar() -> None:
    alvos = {e[0] for e in ESTACOES if e[5] == Papel.ALVO}
    assert alvos == set(LIMIARES) == {"DCSC-00043", "DCSC-00174"}


def test_limiares_de_cada_alvo_sao_estritamente_crescentes() -> None:
    ordem = [Faixa.ATENCAO, Faixa.ALERTA, Faixa.ALERTA_ALTO]
    for codigo, faixas in LIMIARES.items():
        valores = [faixas[f] for f in ordem]
        assert valores == sorted(set(valores)), codigo


def test_coordenadas_plausiveis_para_santa_catarina() -> None:
    for _codigo, _n, _c, lat, lon, _p in ESTACOES + ESTACOES_PDC:
        assert -29.5 < lat < -25.9 and -54.0 < lon < -48.0


def test_reexecutar_nao_sobrescreve_ajuste_manual_de_estacao_nem_de_limiar(s: Session) -> None:
    semear(s)
    s.commit()
    est = s.scalars(select(Estacao).where(Estacao.codigo == "DC-PEU-002")).one()
    est.nome = "Nome ajustado pela equipe"
    est.ativa = False
    pg = s.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one()
    limiar = s.scalars(
        select(Limiar).where(Limiar.estacao_id == pg.id, Limiar.faixa == Faixa.ATENCAO.value)
    ).one()
    limiar.valor_m = 3.9
    s.commit()
    semear(s)
    s.commit()
    s.refresh(est)
    s.refresh(limiar)
    assert est.nome == "Nome ajustado pela equipe" and est.ativa is False
    assert limiar.valor_m == 3.9
    assert s.scalar(select(func.count()).select_from(Estacao)) == 11


def test_cada_fonte_e_cada_estacao_nova_aparece_uma_so_vez_apos_varias_execucoes(
    s: Session,
) -> None:
    for _ in range(3):
        semear(s)
        s.commit()
    for codigo in NOVAS:
        assert s.scalar(select(func.count()).where(Estacao.codigo == codigo)) == 1
    assert s.scalar(select(func.count()).where(Fonte.codigo == "pdc_municipal")) == 1


def test_estacoes_estaduais_continuam_na_fonte_graphql_e_as_do_painel_na_fonte_pdc(
    s: Session,
) -> None:
    semear(s)
    s.commit()
    fonte_de = dict(
        s.execute(
            select(Estacao.codigo, Fonte.codigo).join(Fonte, Fonte.id == Estacao.fonte_id)
        ).all()
    )
    assert {fonte_de[c] for c in NOVAS} == {"pdc_municipal"}
    assert fonte_de["DCSC-00174"] == "dcsc_graphql"  # a Creche nao muda de dona
    assert fonte_de["DCSC-00043"] == "dcsc_graphql"


def test_seed_so_com_o_banco_vazio_de_limiares_recria_apenas_os_que_faltam(s: Session) -> None:
    semear(s)
    s.commit()
    revolver = s.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00174")).one()
    for li in s.scalars(select(Limiar).where(Limiar.estacao_id == revolver.id)):
        if li.faixa == Faixa.ALERTA.value:
            s.delete(li)
    s.commit()
    semear(s)
    s.commit()
    faixas = set(s.scalars(select(Limiar.faixa).where(Limiar.estacao_id == revolver.id)))
    assert faixas == {"atencao", "alerta", "alerta_alto"}
    assert s.scalar(select(func.count()).select_from(Limiar)) == 6
