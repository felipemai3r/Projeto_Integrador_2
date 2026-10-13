"""Qualidade dos dados coletados (RF36, CDU14): fonte instavel, lacunas, sensor travado."""

from datetime import datetime, timedelta

from common.models import Estacao, Fonte, LogColeta
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from api.schemas import EstacaoQualidade, FonteQualidade

FALHAS_PARA_INSTAVEL = 3
LACUNA_MIN = 15  # intervalo sem leitura acima disso conta como lacuna (esperado: 5 min)
TRAVADO_HORAS = 6
VARIAVEIS_DE_SERIE = ("nivel_m", "chuva_acumulada_mm")

_LACUNAS = text("""
    with p as (
        select medido_em,
               medido_em - lag(medido_em) over (order by medido_em) as passo
        from (select distinct medido_em from leitura
              where estacao_id = :est and variavel = :var and medido_em >= :desde) x
    )
    select count(*) filter (where passo > make_interval(mins => :lacuna)),
           coalesce(max(extract(epoch from passo) / 60), 0)
    from p
""")
_COBERTURA = text("""
    select count(distinct date_bin('5 minutes', medido_em, timestamptz '2000-01-01 00:00:00+00'))
    from leitura
    where estacao_id = :est and variavel = :var and medido_em >= :desde and medido_em <= :ate
""")
_QUALIDADE = text("""
    select count(*) filter (where qualidade = 'descartada'),
           count(*) filter (where qualidade = 'suspeita')
    from leitura where estacao_id = :est and variavel = :var and medido_em >= :desde
""")
_TRAVADO = text("""
    select count(*), count(distinct valor) from leitura
    where estacao_id = :est and variavel = 'nivel_m' and qualidade = 'ok' and medido_em >= :desde
""")


def qualidade_das_fontes(s: Session) -> list[FonteQualidade]:
    saida = []
    for f in s.scalars(select(Fonte).where(Fonte.ativa).order_by(Fonte.codigo)):
        logs = list(
            s.scalars(
                select(LogColeta)
                .where(LogColeta.fonte_id == f.id)
                .order_by(LogColeta.executado_em.desc(), LogColeta.id.desc())
                .limit(50)
            )
        )
        falhas = 0
        for lg in logs:
            if lg.status != "falha":
                break
            falhas += 1
        ultimo_ok = next((lg.executado_em for lg in logs if lg.status != "falha"), None)
        saida.append(
            FonteQualidade(
                codigo=f.codigo,
                nome=f.nome,
                ultima_coleta=logs[0].executado_em if logs else None,
                ultimo_sucesso=ultimo_ok,
                status_ultima=logs[0].status if logs else None,
                falhas_seguidas=falhas,
                instavel=falhas >= FALHAS_PARA_INSTAVEL,
                ultima_mensagem=logs[0].mensagem if logs and logs[0].status == "falha" else None,
            )
        )
    return saida


def qualidade_das_estacoes(s: Session, agora: datetime) -> list[EstacaoQualidade]:
    saida = []
    for e in s.scalars(select(Estacao).where(Estacao.ativa).order_by(Estacao.codigo)):
        for var in VARIAVEIS_DE_SERIE:
            ultima = s.execute(
                text("select max(medido_em) from leitura where estacao_id=:e and variavel=:v"),
                {"e": e.id, "v": var},
            ).scalar()
            if ultima is None:
                continue
            desde24, desde7 = agora - timedelta(hours=24), agora - timedelta(days=7)
            cobertos = (
                s.execute(
                    _COBERTURA, {"est": e.id, "var": var, "desde": desde24, "ate": agora}
                ).scalar()
                or 0
            )
            lac, maior = s.execute(
                _LACUNAS, {"est": e.id, "var": var, "desde": desde7, "lacuna": LACUNA_MIN}
            ).one()
            desc, susp = s.execute(_QUALIDADE, {"est": e.id, "var": var, "desde": desde7}).one()
            travado = False
            if var == "nivel_m":
                n, distintos = s.execute(
                    _TRAVADO, {"est": e.id, "desde": agora - timedelta(hours=TRAVADO_HORAS)}
                ).one()
                travado = n >= 60 and distintos == 1
            saida.append(
                EstacaoQualidade(
                    estacao=e.codigo,
                    nome=e.nome,
                    variavel=var,
                    ultima_leitura=ultima,
                    cobertura_24h_pct=round(min(100.0, cobertos / 288 * 100), 1),
                    lacunas_7d=int(lac),
                    maior_lacuna_min=int(maior or 0),
                    possivelmente_travado=travado,
                    descartadas_7d=int(desc),
                    suspeitas_7d=int(susp),
                )
            )
    return saida
