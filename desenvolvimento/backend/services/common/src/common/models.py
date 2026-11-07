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


class InscricaoEmail(Base):
    """Aviso por e-mail. So recebe depois de confirmar pelo link (evita cadastrar terceiros).

    Guarda so o hash do token: o token em si so existe nos links enviados ao proprio e-mail.
    """

    __tablename__ = "inscricao_email"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    estacao_id: Mapped[int | None] = mapped_column(ForeignKey("estacao.id"))
    faixa_minima: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Pedido de mudanca de preferencias de quem JA confirmou. Fica de lado ate o dono clicar no
    # link: a inscricao confirmada segue ativa com as preferencias atuais, e quem so sabe o
    # e-mail dela nao consegue desliga-la nem alterar o que ela recebe.
    token_hash_pendente: Mapped[str | None] = mapped_column(Text, unique=True)
    estacao_id_pendente: Mapped[int | None] = mapped_column(ForeignKey("estacao.id"))
    faixa_minima_pendente: Mapped[str | None] = mapped_column(Text)
    pendente_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Ocorrencia(Base):
    __tablename__ = "ocorrencia"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    ocorreu_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tipo_impacto: Mapped[str] = mapped_column(Text)
    # so em movimento de massa (deslizamento etc.): baixa | media | alta
    gravidade: Mapped[str | None] = mapped_column(Text)
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


class Usuario(Base):
    """Quem pode moderar ou administrar. O cidadao nao tem conta (RN06, RF22)."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    papel: Mapped[str] = mapped_column(Text)  # admin | moderador
    senha_hash: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Moderacao(Base):
    """Historico de moderacao de uma ocorrencia (RF26): nada e sobrescrito sem registro."""

    __tablename__ = "moderacao"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ocorrencia_id: Mapped[int] = mapped_column(ForeignKey("ocorrencia.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    acao: Mapped[str] = mapped_column(Text)  # validar | rejeitar | reclassificar
    status_anterior: Mapped[str] = mapped_column(Text)
    status_novo: Mapped[str] = mapped_column(Text)
    tipo_anterior: Mapped[str] = mapped_column(Text)
    tipo_novo: Mapped[str] = mapped_column(Text)
    gravidade_anterior: Mapped[str | None] = mapped_column(Text)
    gravidade_nova: Mapped[str | None] = mapped_column(Text)
    nota: Mapped[str | None] = mapped_column(Text)
    em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notificacao(Base):
    """Resultado de cada envio de push (CDU07 passo 7): auditoria e aviso de encerramento."""

    __tablename__ = "notificacao"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alerta_id: Mapped[int] = mapped_column(ForeignKey("alerta.id"))
    inscricao_id: Mapped[int] = mapped_column(ForeignKey("inscricao.id"))
    tipo: Mapped[str] = mapped_column(Text)  # abertura | encerramento
    status: Mapped[str] = mapped_column(Text)  # enviada | falha | expirada
    erro: Mapped[str | None] = mapped_column(Text)
    enviada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificacaoEmail(Base):
    """Resultado de cada envio de aviso por e-mail: auditoria e aviso de encerramento."""

    __tablename__ = "notificacao_email"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alerta_id: Mapped[int] = mapped_column(ForeignKey("alerta.id"))
    inscricao_email_id: Mapped[int] = mapped_column(
        ForeignKey("inscricao_email.id", ondelete="CASCADE")
    )
    tipo: Mapped[str] = mapped_column(Text)  # abertura | encerramento
    status: Mapped[str] = mapped_column(Text)  # enviada | falha
    erro: Mapped[str | None] = mapped_column(Text)
    enviada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReacaoOcorrencia(Base):
    """Curtida ("vi tambem") ou denuncia de um registro, uma por aparelho e tipo.

    O aparelho e anonimo: guarda so o hash de um identificador gerado no navegador (RN06).
    """

    __tablename__ = "reacao_ocorrencia"
    __table_args__ = (
        UniqueConstraint("ocorrencia_id", "tipo", "chave_hash", name="uq_reacao_por_aparelho"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ocorrencia_id: Mapped[int] = mapped_column(ForeignKey("ocorrencia.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(Text)  # curtida | denuncia
    chave_hash: Mapped[str] = mapped_column(Text)
    motivo: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
