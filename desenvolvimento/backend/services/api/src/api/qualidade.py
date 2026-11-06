"""Qualidade dos dados coletados (RF36, CDU14): fonte instavel, lacunas, sensor travado."""

from datetime import datetime, timedelta

from common.models import Estacao, Fonte, LogColeta
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from api.consultas import FONTES_MEDIDAS
from api.schemas import EstacaoQualidade, FonteQualidade

FALHAS_PARA_INSTAVEL = 3
LACUNA_MIN = 15  # intervalo sem leitura acima disso conta como lacuna (esperado: 5 min)
TRAVADO_HORAS = 6
# chuva_h001_mm e a unica variavel das estacoes DC-PEU-* (painel municipal). A reanalise ERA5
# grava a mesma variavel, mas nao e medicao: todas as consultas abaixo so olham fontes medidas.
VARIAVEIS_DE_SERIE = ("nivel_m", "chuva_acumulada_mm", "chuva_h001_mm")
FONTES = sorted(FONTES_MEDIDAS)
_MEDIDA = "fonte_id in (select id from fonte where codigo = any(:fontes))"

_LACUNAS = text(f"""
    with p as (
        select medido_em,
               medido_em - lag(medido_em) over (order by medido_em) as passo
        from (select distinct medido_em from leitura
              where estacao_id = :est and variavel = :var and medido_em >= :desde
                and {_MEDIDA}) x
    )
    select count(*) filter (where passo > make_interval(mins => :lacuna)),
           coalesce(max(extract(epoch from passo) / 60), 0)
    from p
""")
_COBERTURA = text(f"""
    select count(distinct date_bin('5 minutes', medido_em, timestamptz '2000-01-01 00:00:00+00'))
    from leitura
    where estacao_id = :est and variavel = :var and medido_em >= :desde and medido_em <= :ate
      and {_MEDIDA}
""")
_QUALIDADE = text(f"""
    select count(*) filter (where qualidade = 'descartada'),
           count(*) filter (where qualidade = 'suspeita')
    from leitura
    where estacao_id = :est and variavel = :var and medido_em >= :desde and {_MEDIDA}
""")
_ULTIMA = text(f"""
    select max(medido_em) from leitura
    where estacao_id = :est and variavel = :var and {_MEDIDA}
""")
# Cobertura = leituras da fonte que mais gravou (duas fontes no mesmo ponto nao dobram a conta);
# o valor unico e conferido entre todas as fontes medidas.
_TRAVADO = text(f"""
    with base as (
        select fonte_id, valor from leitura
        where estacao_id = :est and variavel = 'nivel_m' and qualidade = 'ok'
          and medido_em >= :desde and {_MEDIDA}
    )
    select coalesce((select max(n) from (select count(*) n from base group by fonte_id) x), 0),
           (select count(distinct valor) from base)
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
                _ULTIMA,
                {"est": e.id, "var": var, "fontes": FONTES},
            ).scalar()
            if ultima is None:
                continue
            desde24, desde7 = agora - timedelta(hours=24), agora - timedelta(days=7)
            cobertos = (
                s.execute(
                    _COBERTURA,
                    {"est": e.id, "var": var, "desde": desde24, "ate": agora, "fontes": FONTES},
                ).scalar()
                or 0
            )
            lac, maior = s.execute(
                _LACUNAS,
                {"est": e.id, "var": var, "desde": desde7, "lacuna": LACUNA_MIN, "fontes": FONTES},
            ).one()
            desc, susp = s.execute(
                _QUALIDADE, {"est": e.id, "var": var, "desde": desde7, "fontes": FONTES}
            ).one()
            travado = False
            if var == "nivel_m":
                n, distintos = s.execute(
                    _TRAVADO,
                    {
                        "est": e.id,
                        "desde": agora - timedelta(hours=TRAVADO_HORAS),
                        "fontes": FONTES,
                    },
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
