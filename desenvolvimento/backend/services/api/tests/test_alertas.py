from datetime import UTC, datetime, timedelta

import pytest
from common.enums import Faixa
from common.models import Alerta, Estacao, Fonte, Leitura
from common.seed import semear
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.alertas import Transicao, avaliar_todas, decidir, faixa_vigente

AGORA = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)
LIM = {Faixa.OBSERVACAO: 4.0, Faixa.ATENCAO: 4.5, Faixa.ALERTA: 5.5}
LIMITE = timedelta(minutes=30)


def serie(*niveis: float, idade_min: int = 0) -> list[tuple[datetime, float]]:
    """Da mais recente para a mais antiga, de 5 em 5 minutos."""
    return [(AGORA - timedelta(minutes=idade_min + 5 * i), n) for i, n in enumerate(niveis)]


def test_sobe_de_normal_para_atencao() -> None:
    t = decidir(Faixa.NORMAL, serie(4.62, 4.4, 4.0), LIM, AGORA, LIMITE)
    assert t == Transicao("escala", Faixa.NORMAL, Faixa.ATENCAO)


def test_sobe_direto_para_alerta() -> None:
    t = decidir(Faixa.OBSERVACAO, serie(5.6), LIM, AGORA, LIMITE)
    assert t == Transicao("escala", Faixa.OBSERVACAO, Faixa.ALERTA)


def test_permanecer_na_mesma_faixa_nao_gera_alerta() -> None:
    assert decidir(Faixa.ATENCAO, serie(4.7, 4.6, 4.55), LIM, AGORA, LIMITE) is None


def test_dado_desatualizado_nao_dispara_alerta_nem_encerra() -> None:
    assert decidir(Faixa.NORMAL, serie(5.9, idade_min=90), LIM, AGORA, LIMITE) is None
    assert decidir(Faixa.ALERTA, serie(1.0, 1.0, 1.0, idade_min=90), LIM, AGORA, LIMITE) is None


def test_sem_leitura_ou_sem_limiar_nao_decide() -> None:
    assert decidir(Faixa.NORMAL, [], LIM, AGORA, LIMITE) is None
    assert decidir(Faixa.NORMAL, serie(9.0), {}, AGORA, LIMITE) is None


def test_histerese_uma_leitura_baixa_nao_desce_a_faixa() -> None:
    # estava em alerta; so a leitura mais recente caiu: ainda nao confirma
    assert decidir(Faixa.ALERTA, serie(4.6, 5.7, 5.8), LIM, AGORA, LIMITE) is None


def test_histerese_tres_leituras_baixas_descem_para_a_mais_alta_delas() -> None:
    t = decidir(Faixa.ALERTA, serie(4.4, 4.6, 4.55), LIM, AGORA, LIMITE)
    assert t == Transicao("desce", Faixa.ALERTA, Faixa.ATENCAO)  # a mais alta das 3 e atencao


def test_histerese_poucas_leituras_nao_confirmam() -> None:
    assert decidir(Faixa.ALERTA, serie(3.0, 3.0), LIM, AGORA, LIMITE) is None


def test_oscilacao_em_torno_do_limiar_nao_entra_e_sai() -> None:
    # vigente atencao (4,50); nivel balanca entre 4,49 e 4,51
    assert decidir(Faixa.ATENCAO, serie(4.49, 4.51, 4.49), LIM, AGORA, LIMITE) is None
    assert decidir(Faixa.ATENCAO, serie(4.51, 4.49, 4.51), LIM, AGORA, LIMITE) is None


def test_volta_ao_normal_depois_de_tres_leituras() -> None:
    t = decidir(Faixa.OBSERVACAO, serie(3.5, 3.6, 3.7), LIM, AGORA, LIMITE)
    assert t == Transicao("desce", Faixa.OBSERVACAO, Faixa.NORMAL)


# ---------- persistencia ----------


def _grava(s: Session, codigo: str, niveis_antigo_para_novo: list[float], fim: datetime) -> None:
    est = s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()
    fonte = s.scalars(select(Fonte).where(Fonte.codigo == "dcsc_graphql")).one()
    n = len(niveis_antigo_para_novo)
    for i, v in enumerate(niveis_antigo_para_novo):
        s.add(
            Leitura(
                estacao_id=est.id,
                variavel="nivel_m",
                valor=v,
                unidade="m",
                medido_em=fim - timedelta(minutes=5 * (n - 1 - i)),
                fonte_id=fonte.id,
                qualidade="ok",
            )
        )
    s.commit()


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def _id(s: Session, codigo: str) -> int:
    return s.scalars(select(Estacao.id).where(Estacao.codigo == codigo)).one()


def test_ciclo_completo_subida_descida_e_normal(base: Session) -> None:
    s = base
    # 1) o rio sobe para atencao: abre alerta
    _grava(s, "DCSC-00043", [3.0, 3.5, 4.62], AGORA)
    feitas = avaliar_todas(s, AGORA, LIMITE)
    s.commit()
    assert [(t.tipo, t.para) for _, t, _ in feitas] == [("escala", Faixa.ATENCAO)]
    assert faixa_vigente(s, _id(s, "DCSC-00043")) == Faixa.ATENCAO
    aberto = s.scalars(select(Alerta).where(Alerta.encerrado_em.is_(None))).one()
    assert (aberto.faixa_anterior, aberto.faixa_nova, aberto.origem) == (
        "normal",
        "atencao",
        "observado",
    )

    # 2) reavaliar sem mudanca: nao duplica
    assert avaliar_todas(s, AGORA, LIMITE) == []
    s.commit()
    assert s.scalars(select(Alerta)).all().__len__() == 1

    # 3) sobe para alerta: fecha o anterior e abre outro
    depois = AGORA + timedelta(minutes=5)
    _grava(s, "DCSC-00043", [5.7], depois)
    feitas = avaliar_todas(s, depois, LIMITE)
    s.commit()
    assert feitas[0][2] is not None and feitas[0][2].faixa_nova == "alerta"
    assert faixa_vigente(s, _id(s, "DCSC-00043")) == Faixa.ALERTA
    assert s.scalars(select(Alerta).where(Alerta.encerrado_em.is_(None))).all().__len__() == 1

    # 4) volta ao normal depois de 3 leituras baixas: encerra o episodio, sem novo alerta
    fim = depois + timedelta(minutes=30)
    _grava(s, "DCSC-00043", [3.0, 3.1, 3.0], fim)
    feitas = avaliar_todas(s, fim, LIMITE)
    s.commit()
    assert [(t.tipo, t.para) for _, t, _ in feitas] == [("desce", Faixa.NORMAL)]
    assert feitas[0][2] is None
    assert faixa_vigente(s, _id(s, "DCSC-00043")) == Faixa.NORMAL
    assert s.scalars(select(Alerta).where(Alerta.encerrado_em.is_(None))).all() == []


def test_estacao_sem_leitura_nao_gera_nada(base: Session) -> None:
    assert avaliar_todas(base, AGORA, LIMITE) == []
