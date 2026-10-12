"""Log estruturado em JSON, uma linha por evento. Sem dado pessoal em log."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class FormatadorJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        evento.update(getattr(record, "extra_campos", {}))
        if record.exc_info:
            evento["erro"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar(nivel: str = "INFO") -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(FormatadorJson())
    raiz = logging.getLogger()
    raiz.handlers = [h]
    raiz.setLevel(nivel.upper())
