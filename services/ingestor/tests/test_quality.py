from datetime import UTC, datetime, timedelta

from common.enums import Qualidade, Variavel
from common.schemas import LeituraBruta

from ingestor.quality import avaliar

AGORA = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)


def leitura(variavel: Variavel, valor: float | None, minutos: int = 0) -> LeituraBruta:
    return LeituraBruta(
        estacao_codigo="DCSC-00043",
        variavel=variavel,
        valor=valor,
        unidade="m",
        medido_em=AGORA + timedelta(minutes=minutos),
    )


def test_nivel_normal_e_ok() -> None:
    assert avaliar(leitura(Variavel.NIVEL_M, 1.8), AGORA) == Qualidade.OK


def test_nivel_negativo_ou_acima_de_15m_e_descartado() -> None:
    assert avaliar(leitura(Variavel.NIVEL_M, -0.1), AGORA) == Qualidade.DESCARTADA
    assert avaliar(leitura(Variavel.NIVEL_M, 15.1), AGORA) == Qualidade.DESCARTADA


def test_salto_maior_que_um_metro_em_cinco_minutos_e_suspeito() -> None:
    anterior = (AGORA - timedelta(minutes=5), 1.8)
    assert avaliar(leitura(Variavel.NIVEL_M, 3.0), AGORA, anterior) == Qualidade.SUSPEITA
    assert avaliar(leitura(Variavel.NIVEL_M, 2.5), AGORA, anterior) == Qualidade.OK


def test_salto_grande_apos_lacuna_longa_nao_e_suspeito() -> None:
    anterior = (AGORA - timedelta(hours=3), 1.8)
    assert avaliar(leitura(Variavel.NIVEL_M, 3.0), AGORA, anterior) == Qualidade.OK


def test_horario_no_futuro_e_descartado() -> None:
    assert avaliar(leitura(Variavel.NIVEL_M, 1.8, minutos=30), AGORA) == Qualidade.DESCARTADA


def test_chuva_de_uma_hora_acima_de_150mm_e_suspeita() -> None:
    assert avaliar(leitura(Variavel.CHUVA_H001_MM, 151.0), AGORA) == Qualidade.SUSPEITA
    assert avaliar(leitura(Variavel.CHUVA_H001_MM, 40.0), AGORA) == Qualidade.OK


def test_chuva_negativa_e_valor_nulo_sao_descartados() -> None:
    assert avaliar(leitura(Variavel.CHUVA_H024_MM, -1.0), AGORA) == Qualidade.DESCARTADA
    assert avaliar(leitura(Variavel.NIVEL_M, None), AGORA) == Qualidade.DESCARTADA
