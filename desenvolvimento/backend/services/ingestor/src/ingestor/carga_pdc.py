"""Carga historica da API do painel municipal (PDC), em janelas, por estacao.

Uso: python -m ingestor.carga_pdc [--desde 2025-09-13] [--estacao DC-PEU-002 ...]
A fonte guarda o historico desde 2025-09-13 para todas as estacoes (docs/fontes-de-dados.md,
secao 8.1). Aceita o codigo da API do painel ou o do nosso banco (DC-PEU-001 e DCSC-00174 sao a
mesma estacao). Pode ser reexecutada com seguranca: leitura repetida nao duplica.
O ritmo das chamadas e controlado pelo proprio adaptador (limite de 120 por minuto).
"""

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

from common.config import obter_configuracao
from common.db import sessao
from common.logs import configurar

from ingestor.adapters.pdc import CODIGOS, JANELA_MAX, Pdc, codigo_pdc, janelas
from ingestor.erros import ChaveRecusada, FonteIndisponivel
from ingestor.gravar import gravar

log = logging.getLogger("ingestor.carga_pdc")

INICIO_HISTORICO = date(2025, 9, 13)
DIAS_JANELA = 7  # lotes pequenos: pouca memoria e, se uma janela falhar, perde-se pouco


def carregar(
    pdc: Pdc,
    desde: date = INICIO_HISTORICO,
    ate: datetime | None = None,
    estacoes: list[str] | None = None,
    dias_janela: int = DIAS_JANELA,
    falhas: list[str] | None = None,
) -> dict[str, int]:
    """Baixa e grava o historico. Devolve as leituras novas por estacao (codigo do nosso banco).

    Janela que falha e pulada e anotada em `falhas` (o chamador decide o codigo de saida).
    Chave recusada (401/403) levanta `ChaveRecusada`: continuar so gastaria o limite da fonte.
    """
    tamanho = timedelta(days=dias_janela)
    if not timedelta(days=1) <= tamanho <= JANELA_MAX:
        raise ValueError("dias_janela deve ficar entre 1 e 31")
    codigos = [codigo_pdc(e) for e in estacoes] if estacoes else list(CODIGOS)
    inicio = datetime(desde.year, desde.month, desde.day, tzinfo=UTC)
    fim = ate or datetime.now(UTC)
    todas = list(janelas(inicio, fim, tamanho))
    totais = dict.fromkeys((CODIGOS[c] for c in codigos), 0)
    for codigo in codigos:
        nosso = CODIGOS[codigo]
        n_falhas = 0
        for i, (ini, fim_janela) in enumerate(todas, start=1):
            try:
                leituras = pdc.coletar_estacao(codigo, ini, fim_janela)
            except ChaveRecusada:
                log.error("chave recusada pela fonte; carga interrompida em %s", nosso)
                raise
            except FonteIndisponivel as e:
                n_falhas += 1
                if falhas is not None:
                    falhas.append(f"{nosso} {ini.date()}")
                log.warning("janela ignorada: %s %s: %s", nosso, ini.date(), e)
                continue
            if leituras:
                with sessao() as s:
                    novas, _ = gravar(s, "pdc_municipal", leituras, datetime.now(UTC))
                totais[nosso] += novas
            log.info(
                "%s janela %d/%d (%s): %d lidas, %d novas no total",
                nosso,
                i,
                len(todas),
                ini.date(),
                len(leituras),
                totais[nosso],
            )
        log.info(
            "estacao concluida: %s, %d leituras novas, %d janelas falhas",
            nosso,
            totais[nosso],
            n_falhas,
        )
    return totais


def principal(argv: list[str] | None = None) -> int:
    """Linha de comando. Saida 0 so se TODAS as janelas foram carregadas."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--desde",
        type=date.fromisoformat,
        default=INICIO_HISTORICO,
        help="data inicial (AAAA-MM-DD, UTC); padrao 2025-09-13, inicio do historico da fonte",
    )
    ap.add_argument(
        "--estacao", action="append", help="limita a estacao (repetivel); codigo do painel ou nosso"
    )
    ap.add_argument(
        "--dias-janela", type=int, default=DIAS_JANELA, help="tamanho de cada consulta (1 a 31)"
    )
    args = ap.parse_args(argv)
    cfg = obter_configuracao()
    configurar(cfg.log_level)
    if not cfg.pdc_api_key:
        log.error("PDC_API_KEY vazia: a chave e fornecida pela Defesa Civil municipal")
        return 2
    janelas_falhas: list[str] = []
    try:
        resultado = carregar(
            Pdc(cfg.pdc_api_url, cfg.pdc_api_key),
            desde=args.desde,
            estacoes=args.estacao,
            dias_janela=args.dias_janela,
            falhas=janelas_falhas,
        )
    except ChaveRecusada as e:
        log.error("carga interrompida: %s", e)
        return 3
    for cod, n in resultado.items():
        print(f"{cod}: {n} leituras novas")
    if janelas_falhas:
        # a carga e idempotente: rodar de novo preenche so o que faltou
        log.error("%d janela(s) falharam: %s", len(janelas_falhas), ", ".join(janelas_falhas))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
