from datetime import UTC, datetime, timedelta

from common.enums import StatusColeta, Variavel
from common.models import Leitura, LogColeta
from common.schemas import LeituraBruta
from common.seed import semear
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ingestor.gravar import gravar, registrar_log

AGORA = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)


def serie(
    codigo: str, valores: list[float], variavel: Variavel = Variavel.NIVEL_M
) -> list[LeituraBruta]:
    return [
        LeituraBruta(
            estacao_codigo=codigo,
            variavel=variavel,
            valor=v,
            unidade="m",
            medido_em=AGORA - timedelta(minutes=5 * (len(valores) - i)),
            bruto={"i": i},
        )
        for i, v in enumerate(valores)
    ]


def test_grava_leituras_novas(s: Session) -> None:
    semear(s)
    s.commit()
    inseridas, descartadas = gravar(s, "dcsc_rest", serie("DCSC-00043", [1.7, 1.8, 1.9]), AGORA)
    s.commit()
    assert (inseridas, descartadas) == (3, 0)
    assert s.scalar(select(func.count()).select_from(Leitura)) == 3


def test_reexecutar_nao_duplica(s: Session) -> None:
    semear(s)
    s.commit()
    dados = serie("DCSC-00043", [1.7, 1.8])
    gravar(s, "dcsc_rest", dados, AGORA)
    s.commit()
    inseridas, _ = gravar(s, "dcsc_rest", dados, AGORA)
    s.commit()
    assert inseridas == 0
    assert s.scalar(select(func.count()).select_from(Leitura)) == 2


def test_estacao_nao_configurada_e_ignorada(s: Session) -> None:
    semear(s)
    s.commit()
    inseridas, _ = gravar(s, "dcsc_rest", serie("DCSC-00001", [1.0]), AGORA)
    assert inseridas == 0


def test_leitura_descartada_fica_marcada_e_nao_vira_referencia_de_salto(s: Session) -> None:
    semear(s)
    s.commit()
    # 99.0 e implausivel; 1.9 logo depois nao pode ser suspeito por causa dele
    inseridas, descartadas = gravar(s, "dcsc_rest", serie("DCSC-00043", [1.8, 99.0, 1.9]), AGORA)
    s.commit()
    assert (inseridas, descartadas) == (3, 1)
    q = {x.valor: x.qualidade for x in s.scalars(select(Leitura))}
    assert q == {1.8: "ok", 99.0: "descartada", 1.9: "ok"}


def test_salto_usa_a_ultima_leitura_ja_gravada(s: Session) -> None:
    semear(s)
    s.commit()
    gravar(s, "dcsc_rest", serie("DCSC-00043", [1.8]), AGORA)
    s.commit()
    nova = [
        LeituraBruta(
            estacao_codigo="DCSC-00043",
            variavel=Variavel.NIVEL_M,
            valor=3.5,
            unidade="m",
            medido_em=AGORA,
        )
    ]
    gravar(s, "dcsc_rest", nova, AGORA)
    s.commit()
    suspeitas = s.scalars(select(Leitura).where(Leitura.qualidade == "suspeita")).all()
    assert [x.valor for x in suspeitas] == [3.5]


def test_log_de_coleta_e_gravado(s: Session) -> None:
    semear(s)
    s.commit()
    registrar_log(s, "dcsc_graphql", 120, 9, StatusColeta.SUCESSO, "ok")
    s.commit()
    log = s.scalars(select(LogColeta)).one()
    assert (log.registros, log.status, log.duracao_ms) == (9, "sucesso", 120)
