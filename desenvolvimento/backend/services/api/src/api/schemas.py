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


class AlertaOut(BaseModel):
    """Transicao de faixa de risco. `origem` distingue observado de previsto (RN03)."""

    id: int
    estacao: str
    nome: str
    curso_dagua: str | None
    faixa_anterior: str
    faixa_nova: str
    sobe: bool
    origem: str
    criado_em: datetime
    encerrado_em: datetime | None
    vigente: bool
    nivel_m: float | None = None
    aviso: str = "Estimativa de apoio. A fonte oficial é a Defesa Civil de Presidente Getúlio."


TIPOS_IMPACTO = ("via_intransitavel", "agua_calcada", "agua_imovel", "outro")


class LoginIn(BaseModel):
    email: str
    senha: str


class TokenOut(BaseModel):
    token: str
    nome: str
    papel: str
    expira_em: datetime


class OcorrenciaOut(BaseModel):
    """Ocorrencia registrada pela populacao. Nunca expoe quem registrou (RN06)."""

    id: int
    latitude: float
    longitude: float
    ocorreu_em: datetime
    tipo_impacto: str
    descricao: str | None
    tem_foto: bool
    status: str
    contexto: dict | None
    criada_em: datetime
    moderado_por: str | None = None
    moderado_em: datetime | None = None


class OcorrenciaCriada(BaseModel):
    id: int
    status: str
    mensagem: str


class ModeracaoIn(BaseModel):
    acao: str  # validar | rejeitar | reclassificar
    tipo_impacto: str | None = None
    nota: str | None = None


class ModeracaoOut(BaseModel):
    acao: str
    usuario: str
    status_anterior: str
    status_novo: str
    tipo_anterior: str
    tipo_novo: str
    nota: str | None
    em: datetime


class ChavesPush(BaseModel):
    p256dh: str
    auth: str


class InscricaoIn(BaseModel):
    endpoint: str
    keys: ChavesPush
    estacao: str | None = None  # codigo da estacao; None = todas as estacoes alvo
    faixa_minima: str = "atencao"


class CancelamentoIn(BaseModel):
    endpoint: str


class ChavePublica(BaseModel):
    configurado: bool
    chave_publica: str


class FonteQualidade(BaseModel):
    codigo: str
    nome: str
    ultima_coleta: datetime | None
    ultimo_sucesso: datetime | None
    status_ultima: str | None
    falhas_seguidas: int
    instavel: bool
    ultima_mensagem: str | None


class EstacaoQualidade(BaseModel):
    estacao: str
    nome: str
    variavel: str
    ultima_leitura: datetime | None
    cobertura_24h_pct: float
    lacunas_7d: int
    maior_lacuna_min: int
    possivelmente_travado: bool
    descartadas_7d: int
    suspeitas_7d: int


class Qualidade(BaseModel):
    gerado_em: datetime
    fontes: list[FonteQualidade]
    estacoes: list[EstacaoQualidade]


class ResumoModelo(BaseModel):
    id: int
    treinado_em: datetime
    amostras: int
    rmse_cm: float
    rmse_persistencia_cm: float


class PrevisaoHorizonte(BaseModel):
    horizonte_h: int
    disponivel: bool
    motivo: str | None = None
    valido_para: datetime | None = None
    nivel_m: float | None = None
    incerteza_m: float | None = None
    intervalo_m: tuple[float, float] | None = None
    faixa: str | None = None
    modelo: ResumoModelo | None = None
    extrapolacao: list[str] = []


class PrevisaoOut(BaseModel):
    estacao: str
    origem: str  # operacional | cenario
    base_em: datetime | None
    nivel_base_m: float | None
    horizontes: list[PrevisaoHorizonte]
    aviso: str = (
        "Estimativa de apoio, não é um alerta oficial. A fonte oficial é a Defesa Civil de "
        "Presidente Getúlio."
    )


class SimulacaoIn(BaseModel):
    chuva_mm: dict[str, float]  # codigo da estacao -> mm no periodo
    janela_h: int = 6
    estacao: str = "DCSC-00043"
