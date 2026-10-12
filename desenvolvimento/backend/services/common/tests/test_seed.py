from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.models import Estacao, Fonte, Limiar
from common.seed import semear


def test_seed_cria_estacoes_fontes_e_limiares(s: Session) -> None:
    semear(s)
    s.commit()
    assert s.scalar(select(func.count()).select_from(Estacao)) == 8
    assert s.scalar(select(func.count()).select_from(Fonte)) == 6
    assert s.scalar(select(func.count()).select_from(Limiar)) == 6


def test_seed_e_idempotente(s: Session) -> None:
    semear(s)
    s.commit()
    semear(s)
    s.commit()
    assert s.scalar(select(func.count()).select_from(Estacao)) == 8
    assert s.scalar(select(func.count()).select_from(Limiar)) == 6


def test_limiares_do_rio_dos_indios_sao_crescentes(s: Session) -> None:
    semear(s)
    s.commit()
    est = s.scalar(select(Estacao).where(Estacao.codigo == "DCSC-00043"))
    assert est is not None
    valores = {
        li.faixa: li.valor_m for li in s.scalars(select(Limiar).where(Limiar.estacao_id == est.id))
    }
    assert valores["observacao"] < valores["atencao"] < valores["alerta"]
    assert valores["alerta"] == 5.5
