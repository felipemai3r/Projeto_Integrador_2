"""Interface do adaptador. Todo adaptador implementa isto (RNF11)."""

from abc import ABC, abstractmethod
from datetime import datetime

from common.schemas import LeituraBruta


class Adaptador(ABC):
    codigo: str
    frequencia_s: int

    @abstractmethod
    def coletar(
        self, inicio: datetime | None = None, fim: datetime | None = None
    ) -> list[LeituraBruta]:
        """Busca na fonte e devolve leituras ja no formato interno."""

    @abstractmethod
    def verificar_contrato(self) -> bool:
        """Confere se a resposta real ainda tem a estrutura esperada (canario)."""
