"""Plausibilidade fisica (RF07): limites exatos, folga de 30 s no salto e variaveis sem regra."""

from datetime import UTC, datetime, timedelta

import pytest
from common.enums import Qualidade, Variavel
from common.models import Leitura
from common.schemas import LeituraBruta
from common.seed import semear
from sqlalchemy import select
from sqlalchemy.orm import Session

from ingestor.gravar import gravar
from ingestor.quality import (
    CHUVA_H001_MAX_MM,
    JANELA_SALTO,
    NIVEL_MAX_M,
    SALTO_MAX_M,
    TOLERANCIA_RELOGIO,
    avaliar,
)

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def leitura(variavel: Variavel, valor: float | None, medido_em: datetime = AGORA) -> LeituraBruta:
    return LeituraBruta(
        estacao_codigo="DCSC-00043",
        variavel=variavel,
        valor=valor,
        unidade="m",
        medido_em=medido_em,
    )


def nivel(valor: float, medido_em: datetime = AGORA) -> LeituraBruta:
    return leitura(Variavel.NIVEL_M, valor, medido_em)


def test_constantes_documentadas() -> None:
    assert (NIVEL_MAX_M, SALTO_MAX_M, CHUVA_H001_MAX_MM) == (15.0, 1.0, 150.0)
    assert timedelta(minutes=5, seconds=30) == JANELA_SALTO
    assert timedelta(minutes=2) == TOLERANCIA_RELOGIO


# --- limites do nivel -------------------------------------------------------------------


@pytest.mark.parametrize("valor", [0.0, 15.0, 7.3])
def test_nivel_nos_limites_inclusivos_e_ok(valor: float) -> None:
    assert avaliar(nivel(valor), AGORA) == Qualidade.OK


@pytest.mark.parametrize("valor", [-0.001, 15.001, -100.0, 1000.0])
def test_nivel_fora_de_0_a_15_e_descartado(valor: float) -> None:
    assert avaliar(nivel(valor), AGORA) == Qualidade.DESCARTADA


# --- salto de nivel e a folga de 30 s ---------------------------------------------------


def com_anterior(dt: timedelta, antes: float, agora_: float) -> Qualidade:
    anterior = (AGORA - dt, antes)
    return avaliar(nivel(agora_), AGORA, anterior)


def test_salto_exatamente_igual_ao_limite_nao_e_suspeito() -> None:
    assert com_anterior(timedelta(minutes=5), 2.0, 3.0) == Qualidade.OK


def test_salto_um_milimetro_acima_do_limite_e_suspeito() -> None:
    assert com_anterior(timedelta(minutes=5), 2.0, 3.001) == Qualidade.SUSPEITA


def test_queda_brusca_tambem_e_suspeita() -> None:
    assert com_anterior(timedelta(minutes=5), 3.0, 1.5) == Qualidade.SUSPEITA


@pytest.mark.parametrize(
    "intervalo",
    [
        timedelta(seconds=1),
        timedelta(minutes=5),
        timedelta(minutes=5, milliseconds=19),  # jitter real da API do painel
        timedelta(minutes=5, seconds=29, milliseconds=999),
        timedelta(minutes=5, seconds=30),  # exatamente a janela: ainda conta
    ],
)
def test_salto_dentro_da_janela_de_5min30s_e_suspeito(intervalo: timedelta) -> None:
    assert com_anterior(intervalo, 1.0, 2.5) == Qualidade.SUSPEITA


@pytest.mark.parametrize(
    "intervalo",
    [timedelta(minutes=5, seconds=30, microseconds=1), timedelta(minutes=6), timedelta(hours=2)],
)
def test_salto_depois_da_janela_nao_e_comparavel_e_fica_ok(intervalo: timedelta) -> None:
    assert com_anterior(intervalo, 1.0, 2.5) == Qualidade.OK


@pytest.mark.parametrize("intervalo", [timedelta(0), timedelta(minutes=-5)])
def test_anterior_no_mesmo_instante_ou_no_futuro_nao_gera_suspeita(intervalo: timedelta) -> None:
    """Leitura repetida ou fora de ordem nao e salto: nao ha 'cinco minutos' entre elas."""
    assert com_anterior(intervalo, 1.0, 2.5) == Qualidade.OK


def test_sem_anterior_nao_ha_o_que_comparar() -> None:
    assert avaliar(nivel(9.0), AGORA, None) == Qualidade.OK


def test_fora_da_faixa_vence_o_salto() -> None:
    assert com_anterior(timedelta(minutes=5), 14.0, 16.0) == Qualidade.DESCARTADA


def test_salto_so_vale_para_nivel() -> None:
    anterior = (AGORA - timedelta(minutes=5), 1.0)
    chuva = leitura(Variavel.CHUVA_H001_MM, 90.0)
    assert avaliar(chuva, AGORA, anterior) == Qualidade.OK


# --- chuva ------------------------------------------------------------------------------


def test_chuva_h001_no_teto_e_ok_e_logo_acima_e_suspeita() -> None:
    assert avaliar(leitura(Variavel.CHUVA_H001_MM, 150.0), AGORA) == Qualidade.OK
    assert avaliar(leitura(Variavel.CHUVA_H001_MM, 150.01), AGORA) == Qualidade.SUSPEITA


def test_o_teto_de_150_mm_e_so_da_janela_de_uma_hora() -> None:
    for var in (Variavel.CHUVA_H024_MM, Variavel.CHUVA_H168_MM, Variavel.CHUVA_ACUMULADA_MM):
        assert avaliar(leitura(var, 400.0), AGORA) == Qualidade.OK


@pytest.mark.parametrize(
    "var", [Variavel.CHUVA_H001_MM, Variavel.CHUVA_ACUMULADA_MM, Variavel.CHUVA_H168_MM]
)
def test_chuva_negativa_de_qualquer_janela_e_descartada(var: Variavel) -> None:
    assert avaliar(leitura(var, -0.01), AGORA) == Qualidade.DESCARTADA


def test_chuva_zero_e_ok() -> None:
    assert avaliar(leitura(Variavel.CHUVA_H001_MM, 0.0), AGORA) == Qualidade.OK


# --- relogio ----------------------------------------------------------------------------


def test_tolerancia_de_relogio_de_dois_minutos_e_inclusiva() -> None:
    no_limite = nivel(1.0, AGORA + timedelta(minutes=2))
    passou = nivel(1.0, AGORA + timedelta(minutes=2, seconds=1))
    assert avaliar(no_limite, AGORA) == Qualidade.OK
    assert avaliar(passou, AGORA) == Qualidade.DESCARTADA


def test_futuro_descarta_qualquer_variavel_mesmo_com_valor_plausivel() -> None:
    amanha = AGORA + timedelta(days=1)
    for var in (Variavel.NIVEL_M, Variavel.CHUVA_H001_MM, Variavel.RESERVATORIO_M):
        assert avaliar(leitura(var, 1.0, amanha), AGORA) == Qualidade.DESCARTADA


def test_leitura_antiga_nao_e_penalizada_por_ser_antiga() -> None:
    antiga = nivel(1.0, AGORA - timedelta(days=300))
    assert avaliar(antiga, AGORA) == Qualidade.OK


# --- variaveis sem regra propria --------------------------------------------------------


@pytest.mark.parametrize(
    "var",
    [
        Variavel.RESERVATORIO_M,
        Variavel.RESERVATORIO_PCT,
        Variavel.COMPORTA_GALERIA,
        Variavel.COMPORTA_TULIPA258,
        Variavel.COMPORTA_TULIPA264,
    ],
)
def test_variaveis_sem_regra_passam_como_ok_ate_com_valor_alto(var: Variavel) -> None:
    # cota do reservatorio (273 m) passaria do teto de nivel de rio; nao pode ser descartada
    assert avaliar(leitura(var, 273.95), AGORA) == Qualidade.OK


def test_valor_nulo_e_descartado_para_qualquer_variavel() -> None:
    for var in Variavel:
        assert avaliar(leitura(var, None), AGORA) == Qualidade.DESCARTADA


# --- integracao com a gravacao ----------------------------------------------------------


def serie_pdc(valores: list[float], jitter: timedelta) -> list[LeituraBruta]:
    """Nivel da Creche (DCSC-00174) como o painel entrega: 5 min mais um pequeno jitter."""
    return [
        LeituraBruta(
            estacao_codigo="DCSC-00174",
            variavel=Variavel.NIVEL_M,
            valor=v,
            unidade="m",
            medido_em=AGORA - timedelta(minutes=5 * (len(valores) - i)) + i * jitter,
        )
        for i, v in enumerate(valores)
    ]


def qualidades(s: Session) -> list[str]:
    linhas = s.scalars(select(Leitura).order_by(Leitura.medido_em)).all()
    return [x.qualidade for x in linhas]


def test_gravar_marca_salto_com_jitter_da_api_do_painel_como_suspeito(s: Session) -> None:
    semear(s)
    s.commit()
    # 2,0 -> 3,5 m em ~5 min e 20 ms: sem a folga de 30 s isso passaria como OK
    gravar(s, "pdc_municipal", serie_pdc([2.0, 2.0, 3.5], timedelta(milliseconds=10)), AGORA)
    s.commit()
    assert qualidades(s) == ["ok", "ok", "suspeita"]


def test_gravar_nao_marca_salto_quando_a_lacuna_e_maior_que_a_folga(s: Session) -> None:
    semear(s)
    s.commit()
    dados = serie_pdc([2.0, 2.0, 3.5], timedelta(seconds=40))  # 5 min e ~40 s a mais por passo
    gravar(s, "pdc_municipal", dados, AGORA)
    s.commit()
    assert qualidades(s)[-1] == "ok"
