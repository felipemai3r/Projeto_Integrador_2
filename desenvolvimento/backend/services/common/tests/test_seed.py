from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.models import Estacao, Fonte, Limiar
from common.seed import semear


def test_seed_cria_estacoes_fontes_e_limiares(s: Session) -> None:
    semear(s)
    s.commit()
    assert s.scalar(select(func.count()).select_from(Estacao)) == 11
    assert s.scalar(select(func.count()).select_from(Fonte)) == 7
    assert s.scalar(select(func.count()).select_from(Limiar)) == 6


def test_seed_e_idempotente(s: Session) -> None:
    semear(s)
    s.commit()
    semear(s)
    s.commit()
    assert s.scalar(select(func.count()).select_from(Estacao)) == 11
    assert s.scalar(select(func.count()).select_from(Limiar)) == 6


def test_limiares_do_rio_dos_indios_sao_crescentes(s: Session) -> None:
    semear(s)
    s.commit()
    est = s.scalar(select(Estacao).where(Estacao.codigo == "DCSC-00043"))
    assert est is not None
    valores = {
        li.faixa: li.valor_m for li in s.scalars(select(Limiar).where(Limiar.estacao_id == est.id))
    }
    assert valores["atencao"] < valores["alerta"] < valores["alerta_alto"]
    assert valores["alerta_alto"] == 5.5
    assert "extremo" not in valores  # limiar ainda nao cadastrado


def test_estacoes_do_painel_municipal_so_de_chuva_e_sem_limiar(s: Session) -> None:
    semear(s)
    s.commit()
    pdc = s.scalar(select(Fonte).where(Fonte.codigo == "pdc_municipal"))
    assert pdc is not None and pdc.frequencia_s == 300
    for codigo in ("DC-PEU-002", "DC-PEU-003", "DC-PEU-004"):
        est = s.scalar(select(Estacao).where(Estacao.codigo == codigo))
        assert est is not None
        assert (est.papel, est.curso_dagua, est.fonte_id) == ("influencia", None, pdc.id)
        limiares = select(func.count()).select_from(Limiar).where(Limiar.estacao_id == est.id)
        assert s.scalar(limiares) == 0
    # a Creche do painel (DC-PEU-001) e a DCSC-00174: nao ganha estacao propria
    assert s.scalar(select(Estacao).where(Estacao.codigo == "DC-PEU-001")) is None


def test_seed_sobre_banco_existente_insere_so_o_que_falta(s: Session) -> None:
    semear(s)
    s.commit()
    # simula um banco anterior a fonte PDC: remove-a junto das estacoes novas
    for codigo in ("DC-PEU-002", "DC-PEU-003", "DC-PEU-004"):
        s.delete(s.scalar(select(Estacao).where(Estacao.codigo == codigo)))
    s.delete(s.scalar(select(Fonte).where(Fonte.codigo == "pdc_municipal")))
    s.commit()
    semear(s)
    s.commit()
    assert s.scalar(select(func.count()).select_from(Estacao)) == 11
    assert s.scalar(select(func.count()).select_from(Fonte)) == 7
    assert s.scalar(select(func.count()).select_from(Limiar)) == 6
