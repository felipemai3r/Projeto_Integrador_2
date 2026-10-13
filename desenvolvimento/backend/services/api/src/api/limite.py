"""Limite de requisicoes por chave (janela deslizante, em memoria).

Protege o registro anonimo de ocorrencias e o login (RI05). E por instancia da API: com varias
instancias o limite efetivo e maior, o que e aceitavel na escala atual.
"""

import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import HTTPException, Request


class LimiteTaxa:
    def __init__(self, maximo: int, janela: timedelta) -> None:
        self.maximo = maximo
        self.janela = janela
        self._eventos: dict[str, deque[datetime]] = defaultdict(deque)
        self._trava = threading.Lock()

    def permitir(self, chave: str, agora: datetime) -> bool:
        with self._trava:
            fila = self._eventos[chave]
            while fila and agora - fila[0] > self.janela:
                fila.popleft()
            if len(fila) >= self.maximo:
                return False
            fila.append(agora)
            return True

    def limpar(self) -> None:
        with self._trava:
            self._eventos.clear()


def ip_do_cliente(req: Request) -> str:
    """Atras do Nginx, o IP real vem em X-Forwarded-For (primeiro valor)."""
    encaminhado = req.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return req.client.host if req.client else "desconhecido"


def exigir(limite: LimiteTaxa, chave: str, agora: datetime) -> None:
    if not limite.permitir(chave, agora):
        raise HTTPException(
            429, "Muitas tentativas em pouco tempo. Aguarde um pouco e tente de novo."
        )
