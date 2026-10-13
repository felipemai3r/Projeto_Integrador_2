"""Entidades ORM. Esquema de referencia: docs/arquitetura-desenvolvimento.md, secao 4.

Todo horario e TIMESTAMPTZ em UTC. Latitude e longitude sao numeros simples (sem PostGIS):
a checagem de "ponto dentro do municipio" e feita na aplicacao.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Fonte(Base):
    __tablename__ = "fonte"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nome: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text)
    frequencia_s: Mapped[int] = mapped_column(Integer)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Estacao(Base):
    __tablename__ = "estacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nome: Mapped[str] = mapped_column(Text)
    curso_dagua: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    papel: Mapped[str] = mapped_column(Text)
    fonte_id: Mapped[int | None] = mapped_column(ForeignKey("fonte.id"))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Leitura(Base):
    __tablename__ = "leitura"
    __table_args__ = (
        UniqueConstraint("estacao_id", "variavel", "medido_em", "fonte_id"),
        Index("idx_leitura_consulta", "estacao_id", "variavel", "medido_em"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estacao_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    variavel: Mapped[str] = mapped_column(Text)
    valor: Mapped[float | None] = mapped_column(Double)
    unidade: Mapped[str] = mapped_column(Text)
    medido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    fonte_id: Mapped[int] = mapped_column(ForeignKey("fonte.id"))
    qualidade: Mapped[str] = mapped_column(Text, default="ok", server_default="ok")
    bruto: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class PrevisaoChuva(Base):
    __tablename__ = "previsao_chuva"
    __table_args__ = (UniqueConstraint("estacao_id", "gerado_em", "valido_para", "modelo_fonte"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estacao_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    gerado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valido_para: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    chuva_mm: Mapped[float] = mapped_column(Double)
    probabilidade: Mapped[float | None] = mapped_column(Double)
    modelo_fonte: Mapped[str] = mapped_column(Text)


class Limiar(Base):
    __tablename__ = "limiar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estacao_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    faixa: Mapped[str] = mapped_column(Text)
    valor_m: Mapped[float] = mapped_column(Double)
    vigente_desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    autor: Mapped[str] = mapped_column(Text)
    justificativa: Mapped[str] = mapped_column(Text)


class Modelo(Base):
    __tablename__ = "modelo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estacao_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    horizonte_h: Mapped[int] = mapped_column(Integer)
    algoritmo: Mapped[str] = mapped_column(Text)
    treinado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amostras: Mapped[int] = mapped_column(Integer)
    rmse_cm: Mapped[float] = mapped_column(Double)
    mae_cm: Mapped[float] = mapped_column(Double)
    rmse_persistencia_cm: Mapped[float] = mapped_column(Double)
    publicado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    caminho_artefato: Mapped[str] = mapped_column(Text)
    metadados: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class PrevisaoNivel(Base):
    __tablename__ = "previsao_nivel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estacao_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    modelo_id: Mapped[int] = mapped_column(ForeignKey("modelo.id"))
    gerado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valido_para: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    nivel_m: Mapped[float] = mapped_column(Double)
    incerteza_m: Mapped[float] = mapped_column(Double)
    origem: Mapped[str] = mapped_column(Text)


class Alerta(Base):
    __tablename__ = "alerta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estacao_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    faixa_anterior: Mapped[str] = mapped_column(Text)
    faixa_nova: Mapped[str] = mapped_column(Text)
    severidade: Mapped[str] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    encerrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Inscricao(Base):
    __tablename__ = "inscricao"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    chave_p256dh: Mapped[str] = mapped_column(Text)
    chave_auth: Mapped[str] = mapped_column(Text)
    estacao_id: Mapped[int | None] = mapped_column(ForeignKey("estacao.id"))
    faixa_minima: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Ocorrencia(Base):
    __tablename__ = "ocorrencia"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    ocorreu_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tipo_impacto: Mapped[str] = mapped_column(Text)
    descricao: Mapped[str | None] = mapped_column(Text)
    foto_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pendente", server_default="pendente")
    moderado_por: Mapped[str | None] = mapped_column(Text)
    moderado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contexto: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LogColeta(Base):
    __tablename__ = "log_coleta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fonte_id: Mapped[int] = mapped_column(ForeignKey("fonte.id"))
    executado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    duracao_ms: Mapped[int] = mapped_column(Integer)
    registros: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    mensagem: Mapped[str | None] = mapped_column(Text)


class Correlacao(Base):
    """Resultado da analise de correlacao defasada (RF13), um por ponto e rodada."""

    __tablename__ = "correlacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    estacao_alvo_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    ponto_id: Mapped[int] = mapped_column(ForeignKey("estacao.id"))
    explicativa: Mapped[str] = mapped_column(Text)
    janela_chuva_h: Mapped[int] = mapped_column(Integer)
    melhor_defasagem_h: Mapped[int] = mapped_column(Integer)
    r: Mapped[float] = mapped_column(Double)
    ic_inf: Mapped[float | None] = mapped_column(Double)
    ic_sup: Mapped[float | None] = mapped_column(Double)
    p_valor: Mapped[float | None] = mapped_column(Double)
    horas_validas: Mapped[int] = mapped_column(Integer)
    curva: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    metodo: Mapped[str] = mapped_column(Text)
    periodo_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    periodo_fim: Mapped[datetime] = mapped_column(DateTime(timezone=True))
