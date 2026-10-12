"""Contratos Pydantic entre adaptadores, ingestao e API."""

from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict

from common.enums import Variavel


class LeituraBruta(BaseModel):
    """Leitura ja no formato interno, produzida por um adaptador."""

    model_config = ConfigDict(frozen=True)

    estacao_codigo: str
    variavel: Variavel
    valor: float | None
    unidade: str
    medido_em: AwareDatetime
    bruto: dict[str, Any] | None = None


class ResultadoColeta(BaseModel):
    fonte_codigo: str
    leituras: list[LeituraBruta]
    duracao_ms: int
    iniciado_em: datetime


class PrevisaoChuvaBruta(BaseModel):
    """Chuva prevista para uma estacao em um instante futuro, por modelo."""

    model_config = ConfigDict(frozen=True)

    estacao_codigo: str
    gerado_em: AwareDatetime
    valido_para: AwareDatetime
    chuva_mm: float
    probabilidade: float | None = None
    modelo_fonte: str
