"""Contratos de resposta da API. Todo dado externo traz fonte, estacao e medido_em (RNF16)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EstadoDado = Literal["ok", "desatualizado", "indisponivel"]


class Limiares(BaseModel):
    observacao: float | None = None
    atencao: float | None = None
    alerta: float | None = None


class EstacaoOut(BaseModel):
    codigo: str
    nome: str
    curso_dagua: str | None
    papel: str
    latitude: float
    longitude: float
    limiares: Limiares


class NivelAtual(BaseModel):
    estacao: EstacaoOut
    estado: EstadoDado
    motivo: str | None = None
    nivel_m: float | None = None
    faixa: str | None = None
    taxa_cm_h: float | None = None
    aceleracao_cm_h2: float | None = None
    tendencia: str | None = None
    medido_em: datetime | None = None
    fonte: str | None = None


class PontoSerie(BaseModel):
    medido_em: datetime
    valor: float


class Serie(BaseModel):
    estacao: str
    variavel: str
    unidade: str
    passo_min: int
    pontos: list[PontoSerie]


class ChuvaEstacao(BaseModel):
    estacao: str
    nome: str
    papel: str
    estado: EstadoDado
    medido_em: datetime | None
    fonte: str | None
    acumulado_mm: dict[str, float | None]


class CorrelacaoOut(BaseModel):
    """Um resultado da correlacao defasada (RF13). Exploratorio: leia `leitura`."""

    ponto: str
    nome: str
    explicativa: str
    melhor_defasagem_h: int
    r: float
    ic_inf: float | None
    ic_sup: float | None
    p_valor: float | None
    horas_validas: int
    sinal_claro: bool
    leitura: str
    janela_chuva_h: int
    periodo_inicio: datetime
    periodo_fim: datetime
    calculado_em: datetime
