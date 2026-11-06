"""Alertas por nivel observado: histerese, fronteira de dado velho, Revolver e episodios."""

from datetime import UTC, datetime, timedelta

import pytest
from common.enums import Faixa
from common.models import Alerta, Estacao, Fonte, Leitura
from common.seed import semear
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.alertas import (
    LEITURAS_PARA_DESCER,
    Transicao,
    alerta_aberto,
    aplicar,
    avaliar_estacao,
    avaliar_todas,
    decidir,
    faixa_vigente,
)

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
LIM = {Faixa.ATENCAO: 4.0, Faixa.ALERTA: 4.5, Faixa.ALERTA_ALTO: 5.5}
LIM_X = {**LIM, Faixa.EXTREMO: 7.0}
LIMITE = timedelta(minutes=30)


def serie(*niveis: float, idade_min: float = 0) -> list[tuple[datetime, float]]:
    """Da mais recente para a mais antiga, de 5 em 5 minutos."""
    return [(AGORA - timedelta(minutes=idade_min + 5 * i), n) for i, n in enumerate(niveis)]


# ---------- decidir: escalada ----------


def test_uma_unica_leitura_alta_basta_para_subir_sem_histerese() -> None:
    assert decidir(Faixa.NORMAL, serie(5.6), LIM, AGORA, LIMITE) == Transicao(
        "escala", Faixa.NORMAL, Faixa.ALERTA_ALTO
    )


def test_subida_ignora_as_leituras_anteriores_e_olha_so_a_mais_recente() -> None:
    assert decidir(Faixa.ATENCAO, serie(4.6, 1.0, 1.0), LIM, AGORA, LIMITE) == Transicao(
        "escala", Faixa.ATENCAO, Faixa.ALERTA
    )


def test_sobe_para_extremo_quando_ha_limiar_cadastrado() -> None:
    t = decidir(Faixa.ALERTA_ALTO, serie(7.0), LIM_X, AGORA, LIMITE)
    assert t == Transicao("escala", Faixa.ALERTA_ALTO, Faixa.EXTREMO)


def test_sem_limiar_de_extremo_o_nivel_altissimo_fica_em_alerta_alto() -> None:
    assert decidir(Faixa.ALERTA_ALTO, serie(30.0), LIM, AGORA, LIMITE) is None


def test_leitura_no_limiar_exato_conta_como_atingida() -> None:
    assert decidir(Faixa.NORMAL, serie(4.0), LIM, AGORA, LIMITE) == Transicao(
        "escala", Faixa.NORMAL, Faixa.ATENCAO
    )
    assert decidir(Faixa.NORMAL, serie(3.999), LIM, AGORA, LIMITE) is None


# ---------- decidir: dado velho (RN04) ----------


def test_dado_exatamente_no_limite_de_idade_ainda_decide() -> None:
    assert decidir(Faixa.NORMAL, serie(5.0, idade_min=30), LIM, AGORA, LIMITE) is not None


def test_dado_um_segundo_alem_do_limite_nao_decide() -> None:
    velho = serie(5.0, idade_min=30 + 1 / 60)
    assert decidir(Faixa.NORMAL, velho, LIM, AGORA, LIMITE) is None


def test_so_a_leitura_mais_recente_define_se_o_dado_esta_velho() -> None:
    # a mais recente esta fresca; as outras sao velhas: a idade conta so a primeira
    leituras = [(AGORA, 5.0), (AGORA - timedelta(hours=5), 1.0)]
    assert decidir(Faixa.NORMAL, leituras, LIM, AGORA, LIMITE) is not None


# ---------- decidir: histerese (RN10) ----------


def test_descida_considera_somente_as_tres_leituras_mais_recentes() -> None:
    # a 4a leitura (antiga) estava alta, mas nao entra na conta
    t = decidir(Faixa.ALERTA_ALTO, serie(3.0, 3.1, 3.2, 6.0), LIM, AGORA, LIMITE)
    assert t == Transicao("desce", Faixa.ALERTA_ALTO, Faixa.NORMAL)
    assert LEITURAS_PARA_DESCER == 3


def test_descida_nao_ocorre_se_alguma_das_tres_ainda_esta_na_faixa_vigente() -> None:
    assert decidir(Faixa.ALERTA, serie(3.0, 4.6, 3.0), LIM, AGORA, LIMITE) is None
    assert decidir(Faixa.ALERTA, serie(3.0, 3.0, 4.5), LIM, AGORA, LIMITE) is None  # no limiar


def test_descida_nao_ocorre_se_alguma_das_tres_esta_acima_da_vigente() -> None:
    # vigente atencao; leitura recente normal, mas uma das tres ja estava em alerta
    assert decidir(Faixa.ATENCAO, serie(3.0, 4.6, 3.0), LIM, AGORA, LIMITE) is None


def test_descida_vai_para_a_mais_alta_das_tres_e_nao_direto_ao_normal() -> None:
    t = decidir(Faixa.ALERTA_ALTO, serie(3.0, 4.2, 3.5), LIM, AGORA, LIMITE)
    assert t == Transicao("desce", Faixa.ALERTA_ALTO, Faixa.ATENCAO)


def test_descida_do_extremo_para_alerta_alto() -> None:
    t = decidir(Faixa.EXTREMO, serie(5.6, 5.7, 5.8), LIM_X, AGORA, LIMITE)
    assert t == Transicao("desce", Faixa.EXTREMO, Faixa.ALERTA_ALTO)


def test_com_duas_leituras_nao_ha_histerese_possivel() -> None:
    assert decidir(Faixa.ALERTA, serie(3.0, 3.0), LIM, AGORA, LIMITE) is None
    assert decidir(Faixa.ALERTA, serie(3.0), LIM, AGORA, LIMITE) is None


def test_mesma_faixa_da_vigente_nunca_gera_transicao() -> None:
    for vigente, nivel in [(Faixa.NORMAL, 1.0), (Faixa.ATENCAO, 4.1), (Faixa.ALERTA_ALTO, 9.0)]:
        assert decidir(vigente, serie(nivel, nivel, nivel), LIM, AGORA, LIMITE) is None


def test_leituras_vazias_ou_limiares_vazios_nunca_decidem() -> None:
    assert decidir(Faixa.ALERTA, [], LIM, AGORA, LIMITE) is None
    assert decidir(Faixa.ALERTA, serie(9.0, 9.0, 9.0), {}, AGORA, LIMITE) is None


# ---------- persistencia ----------


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def _est(s: Session, codigo: str) -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()


def _grava(s: Session, codigo: str, niveis: list[float], fim: datetime) -> None:
    """`niveis` do mais antigo para o mais novo; a ultima leitura e em `fim`."""
    est, fonte = (
        _est(s, codigo),
        s.scalars(select(Fonte).where(Fonte.codigo == "dcsc_graphql")).one(),
    )
    n = len(niveis)
    for i, v in enumerate(niveis):
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


def test_revolver_e_rio_dos_indios_alertam_de_forma_independente(base: Session) -> None:
    # 3,2 m: normal no rio dos Indios (limiar 4,0), alerta no Revolver (limiar 3,0)
    _grava(base, "DCSC-00043", [3.2, 3.2, 3.2], AGORA)
    _grava(base, "DCSC-00174", [3.2, 3.2, 3.2], AGORA)
    feitas = avaliar_todas(base, AGORA, LIMITE)
    base.commit()
    assert [(e.codigo, t.para) for e, t, _ in feitas] == [("DCSC-00174", Faixa.ALERTA)]
    assert faixa_vigente(base, _est(base, "DCSC-00043").id) == Faixa.NORMAL
    assert faixa_vigente(base, _est(base, "DCSC-00174").id) == Faixa.ALERTA


def test_estacao_de_influencia_e_serra_nunca_geram_alerta_mesmo_com_nivel_alto(
    base: Session,
) -> None:
    _grava(base, "DCSC-00021", [30.0, 30.0, 30.0], AGORA)  # Boiteux: influencia, sem limiar
    _grava(base, "DC-PEU-003", [30.0, 30.0, 30.0], AGORA)
    assert avaliar_todas(base, AGORA, LIMITE) == []
    assert base.scalars(select(Alerta)).all() == []


def test_estacao_alvo_inativa_e_ignorada(base: Session) -> None:
    _est(base, "DCSC-00174").ativa = False
    base.commit()
    _grava(base, "DCSC-00174", [3.6, 3.6, 3.6], AGORA)
    assert avaliar_todas(base, AGORA, LIMITE) == []


def test_dado_velho_nao_encerra_alerta_aberto(base: Session) -> None:
    _grava(base, "DCSC-00174", [3.2, 3.2, 3.2], AGORA)
    avaliar_todas(base, AGORA, LIMITE)
    base.commit()
    mais_tarde = AGORA + timedelta(hours=3)  # leituras antigas dariam "normal" se fossem validas
    _grava(base, "DCSC-00174", [1.0, 1.0, 1.0], AGORA + timedelta(minutes=15))
    assert avaliar_todas(base, mais_tarde, LIMITE) == []
    assert alerta_aberto(base, _est(base, "DCSC-00174").id) is not None


def test_descida_para_faixa_nao_normal_fecha_o_alerta_e_abre_outro_sem_ser_subida(
    base: Session,
) -> None:
    pg = _est(base, "DCSC-00043").id
    _grava(base, "DCSC-00043", [5.7], AGORA)
    avaliar_todas(base, AGORA, LIMITE)
    base.commit()
    depois = AGORA + timedelta(minutes=30)
    _grava(base, "DCSC-00043", [4.6, 4.6, 4.6], depois)
    feitas = avaliar_todas(base, depois, LIMITE)
    base.commit()
    assert [(t.tipo, t.de, t.para) for _, t, _ in feitas] == [
        ("desce", Faixa.ALERTA_ALTO, Faixa.ALERTA)
    ]
    novo = feitas[0][2]
    assert novo is not None and (novo.faixa_anterior, novo.faixa_nova) == ("alerta_alto", "alerta")
    alertas = base.scalars(select(Alerta).where(Alerta.estacao_id == pg).order_by(Alerta.id)).all()
    assert [a.encerrado_em is not None for a in alertas] == [True, False]
    assert faixa_vigente(base, pg) == Faixa.ALERTA


def test_aplicar_volta_ao_normal_so_fecha_o_episodio_e_nao_cria_alerta(base: Session) -> None:
    est = _est(base, "DCSC-00043")
    abre = aplicar(base, est.id, Transicao("escala", Faixa.NORMAL, Faixa.ATENCAO), AGORA)
    assert abre is not None and abre.encerrado_em is None and abre.origem == "observado"
    assert abre.severidade == "atencao" and abre.criado_em == AGORA
    fim = AGORA + timedelta(hours=1)
    assert aplicar(base, est.id, Transicao("desce", Faixa.ATENCAO, Faixa.NORMAL), fim) is None
    assert abre.encerrado_em == fim and alerta_aberto(base, est.id) is None


def test_aplicar_sem_alerta_aberto_apenas_cria_o_novo(base: Session) -> None:
    est = _est(base, "DCSC-00043")
    novo = aplicar(base, est.id, Transicao("escala", Faixa.NORMAL, Faixa.ALERTA), AGORA)
    assert novo is not None and base.scalars(select(Alerta)).all() == [novo]


def test_aplicar_encerra_so_o_alerta_da_propria_estacao(base: Session) -> None:
    pg, rev = _est(base, "DCSC-00043"), _est(base, "DCSC-00174")
    do_rev = aplicar(base, rev.id, Transicao("escala", Faixa.NORMAL, Faixa.ATENCAO), AGORA)
    aplicar(base, pg.id, Transicao("escala", Faixa.NORMAL, Faixa.ATENCAO), AGORA)
    aplicar(
        base, pg.id, Transicao("desce", Faixa.ATENCAO, Faixa.NORMAL), AGORA + timedelta(hours=1)
    )
    assert do_rev is not None and do_rev.encerrado_em is None


def test_faixa_vigente_sem_alerta_aberto_e_normal(base: Session) -> None:
    assert faixa_vigente(base, _est(base, "DCSC-00043").id) == Faixa.NORMAL


def test_avaliar_estacao_sem_leitura_ou_sem_limiar_devolve_none(base: Session) -> None:
    assert avaliar_estacao(base, _est(base, "DCSC-00043"), AGORA, LIMITE) is None
    _grava(base, "DCSC-00021", [30.0], AGORA)  # sem limiares cadastrados
    assert avaliar_estacao(base, _est(base, "DCSC-00021"), AGORA, LIMITE) is None


def test_leitura_suspeita_nao_dispara_alerta(base: Session) -> None:
    est, fonte = _est(base, "DCSC-00174"), base.scalars(select(Fonte)).first()
    base.add(
        Leitura(
            estacao_id=est.id,
            variavel="nivel_m",
            valor=9.0,
            unidade="m",
            medido_em=AGORA,
            fonte_id=fonte.id,
            qualidade="suspeita",
        )
    )
    base.commit()
    assert avaliar_todas(base, AGORA, LIMITE) == []
