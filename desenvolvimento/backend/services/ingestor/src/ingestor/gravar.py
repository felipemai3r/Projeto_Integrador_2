"""Gravacao idempotente de leituras e log de coleta."""

from collections import defaultdict
from datetime import datetime

from common.enums import Qualidade, StatusColeta
from common.models import Estacao, Fonte, Leitura, LogColeta, PrevisaoChuva
from common.schemas import LeituraBruta, PrevisaoChuvaBruta
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ingestor.quality import avaliar

LOTE = 5000


def _anterior_no_banco(
    s: Session, estacao_id: int, variavel: str, antes_de: datetime
) -> tuple[datetime, float] | None:
    linha = s.execute(
        select(Leitura.medido_em, Leitura.valor)
        .where(
            Leitura.estacao_id == estacao_id,
            Leitura.variavel == variavel,
            Leitura.medido_em < antes_de,
            Leitura.valor.is_not(None),
            Leitura.qualidade != Qualidade.DESCARTADA.value,
        )
        .order_by(Leitura.medido_em.desc())
        .limit(1)
    ).first()
    return (linha[0], linha[1]) if linha else None


def gravar(
    s: Session, fonte_codigo: str, leituras: list[LeituraBruta], agora: datetime
) -> tuple[int, int]:
    """Grava as leituras novas das estacoes ativas. Devolve (inseridas, descartadas).

    Reexecutar com os mesmos dados nao duplica (UNIQUE + ON CONFLICT DO NOTHING).
    """
    fonte_id = s.scalar(select(Fonte.id).where(Fonte.codigo == fonte_codigo))
    if fonte_id is None:
        raise LookupError(f"fonte desconhecida: {fonte_codigo} (rode o seed)")
    ids = {e.codigo: e.id for e in s.scalars(select(Estacao).where(Estacao.ativa))}

    series: dict[tuple[str, str], list[LeituraBruta]] = defaultdict(list)
    for leitura in leituras:
        if leitura.estacao_codigo in ids:
            series[(leitura.estacao_codigo, leitura.variavel.value)].append(leitura)

    linhas: list[dict[str, object]] = []
    descartadas = 0
    for (codigo, variavel), pontos in series.items():
        pontos.sort(key=lambda p: p.medido_em)
        anterior = _anterior_no_banco(s, ids[codigo], variavel, pontos[0].medido_em)
        for p in pontos:
            q = avaliar(p, agora, anterior)
            descartadas += q == Qualidade.DESCARTADA
            if q != Qualidade.DESCARTADA and p.valor is not None:
                anterior = (p.medido_em, p.valor)
            linhas.append(
                {
                    "estacao_id": ids[codigo],
                    "variavel": variavel,
                    "valor": p.valor,
                    "unidade": p.unidade,
                    "medido_em": p.medido_em,
                    "fonte_id": fonte_id,
                    "qualidade": q.value,
                    "bruto": p.bruto,
                }
            )

    inseridas = 0
    for i in range(0, len(linhas), LOTE):
        # rowcount nao e confiavel em INSERT multiplo; RETURNING conta so as linhas realmente novas
        novas = s.execute(
            insert(Leitura)
            .values(linhas[i : i + LOTE])
            .on_conflict_do_nothing(
                index_elements=["estacao_id", "variavel", "medido_em", "fonte_id"]
            )
            .returning(Leitura.id)
        ).all()
        inseridas += len(novas)
    return inseridas, descartadas


def gravar_previsoes(
    s: Session, fonte_codigo: str, previsoes: list[PrevisaoChuvaBruta], agora: datetime
) -> tuple[int, int]:
    """Grava previsoes de chuva. Mesma assinatura de `gravar`: (inseridas, descartadas=0)."""
    ids = {e.codigo: e.id for e in s.scalars(select(Estacao).where(Estacao.ativa))}
    linhas = [
        {
            "estacao_id": ids[p.estacao_codigo],
            "gerado_em": p.gerado_em,
            "valido_para": p.valido_para,
            "chuva_mm": p.chuva_mm,
            "probabilidade": p.probabilidade,
            "modelo_fonte": p.modelo_fonte,
        }
        for p in previsoes
        if p.estacao_codigo in ids
    ]
    inseridas = 0
    for i in range(0, len(linhas), LOTE):
        novas = s.execute(
            insert(PrevisaoChuva)
            .values(linhas[i : i + LOTE])
            .on_conflict_do_nothing(
                index_elements=["estacao_id", "gerado_em", "valido_para", "modelo_fonte"]
            )
            .returning(PrevisaoChuva.id)
        ).all()
        inseridas += len(novas)
    return inseridas, 0


def registrar_log(
    s: Session,
    fonte_codigo: str,
    duracao_ms: int,
    registros: int,
    status: StatusColeta,
    mensagem: str | None = None,
) -> None:
    fonte_id = s.scalar(select(Fonte.id).where(Fonte.codigo == fonte_codigo))
    if fonte_id is None:
        return
    s.add(
        LogColeta(
            fonte_id=fonte_id,
            duracao_ms=duracao_ms,
            registros=registros,
            status=status.value,
            mensagem=mensagem[:1000] if mensagem else None,
        )
    )
