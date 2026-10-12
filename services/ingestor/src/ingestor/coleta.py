"""Execucao de uma coleta com log de auditoria (RF35) e tolerancia a falha (RNF05)."""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from common.db import sessao
from common.enums import StatusColeta
from common.schemas import LeituraBruta

from ingestor.erros import ContratoQuebrado, FonteIndisponivel
from ingestor.gravar import gravar, registrar_log

log = logging.getLogger("ingestor.coleta")


def executar(fonte_codigo: str, buscar: Callable[[], list[LeituraBruta]]) -> StatusColeta:
    """Roda `buscar`, grava o resultado e registra o log. Nunca propaga excecao de fonte."""
    t0 = time.monotonic()
    agora = datetime.now(UTC)
    status, registros, mensagem = StatusColeta.FALHA, 0, None
    try:
        leituras = buscar()
        with sessao() as s:
            inseridas, descartadas = gravar(s, fonte_codigo, leituras, agora)
        registros = inseridas
        status = StatusColeta.SUCESSO if inseridas else StatusColeta.VAZIO
        mensagem = f"{len(leituras)} lidas, {inseridas} novas, {descartadas} descartadas"
    except (FonteIndisponivel, ContratoQuebrado) as e:
        mensagem = f"{type(e).__name__}: {e}"
        log.warning(
            "coleta falhou", extra={"extra_campos": {"fonte": fonte_codigo, "erro": mensagem}}
        )
    except Exception as e:  # noqa: BLE001  (um job nao pode derrubar o agendador)
        mensagem = f"erro inesperado {type(e).__name__}: {e}"
        log.exception("erro inesperado na coleta", extra={"extra_campos": {"fonte": fonte_codigo}})

    duracao_ms = int((time.monotonic() - t0) * 1000)
    try:
        with sessao() as s:
            registrar_log(s, fonte_codigo, duracao_ms, registros, status, mensagem)
    except Exception:
        log.exception("nao foi possivel registrar o log de coleta")
    log.info(
        "coleta concluida",
        extra={
            "extra_campos": {
                "fonte": fonte_codigo,
                "status": status.value,
                "registros": registros,
                "duracao_ms": duracao_ms,
            }
        },
    )
    return status
