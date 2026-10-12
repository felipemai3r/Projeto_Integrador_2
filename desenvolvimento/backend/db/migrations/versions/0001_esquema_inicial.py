"""esquema inicial

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fonte",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("frequencia_s", sa.Integer(), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_table(
        "ocorrencia",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("ocorreu_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tipo_impacto", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("foto_path", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pendente", nullable=False),
        sa.Column("moderado_por", sa.Text(), nullable=True),
        sa.Column("moderado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contexto", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "estacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("curso_dagua", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("papel", sa.Text(), nullable=False),
        sa.Column("fonte_id", sa.Integer(), nullable=True),
        sa.Column("ativa", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["fonte_id"],
            ["fonte.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_table(
        "log_coleta",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fonte_id", sa.Integer(), nullable=False),
        sa.Column(
            "executado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("registros", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["fonte_id"],
            ["fonte.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alerta",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("estacao_id", sa.Integer(), nullable=False),
        sa.Column("faixa_anterior", sa.Text(), nullable=False),
        sa.Column("faixa_nova", sa.Text(), nullable=False),
        sa.Column("severidade", sa.Text(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["estacao_id"],
            ["estacao.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "inscricao",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("chave_p256dh", sa.Text(), nullable=False),
        sa.Column("chave_auth", sa.Text(), nullable=False),
        sa.Column("estacao_id", sa.Integer(), nullable=True),
        sa.Column("faixa_minima", sa.Text(), nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ativa", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["estacao_id"],
            ["estacao.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_table(
        "leitura",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("estacao_id", sa.Integer(), nullable=False),
        sa.Column("variavel", sa.Text(), nullable=False),
        sa.Column("valor", sa.Double(), nullable=True),
        sa.Column("unidade", sa.Text(), nullable=False),
        sa.Column("medido_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "coletado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fonte_id", sa.Integer(), nullable=False),
        sa.Column("qualidade", sa.Text(), server_default="ok", nullable=False),
        sa.Column("bruto", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["estacao_id"],
            ["estacao.id"],
        ),
        sa.ForeignKeyConstraint(
            ["fonte_id"],
            ["fonte.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("estacao_id", "variavel", "medido_em", "fonte_id"),
    )
    op.create_index(
        "idx_leitura_consulta",
        "leitura",
        ["estacao_id", "variavel", "medido_em"],
        unique=False,
    )
    op.create_table(
        "limiar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("estacao_id", sa.Integer(), nullable=False),
        sa.Column("faixa", sa.Text(), nullable=False),
        sa.Column("valor_m", sa.Double(), nullable=False),
        sa.Column(
            "vigente_desde",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("autor", sa.Text(), nullable=False),
        sa.Column("justificativa", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["estacao_id"],
            ["estacao.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "modelo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("estacao_id", sa.Integer(), nullable=False),
        sa.Column("horizonte_h", sa.Integer(), nullable=False),
        sa.Column("algoritmo", sa.Text(), nullable=False),
        sa.Column("treinado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amostras", sa.Integer(), nullable=False),
        sa.Column("rmse_cm", sa.Double(), nullable=False),
        sa.Column("mae_cm", sa.Double(), nullable=False),
        sa.Column("rmse_persistencia_cm", sa.Double(), nullable=False),
        sa.Column("publicado", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("caminho_artefato", sa.Text(), nullable=False),
        sa.Column("metadados", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["estacao_id"],
            ["estacao.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "previsao_chuva",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("estacao_id", sa.Integer(), nullable=False),
        sa.Column("gerado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valido_para", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chuva_mm", sa.Double(), nullable=False),
        sa.Column("probabilidade", sa.Double(), nullable=True),
        sa.Column("modelo_fonte", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["estacao_id"],
            ["estacao.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("estacao_id", "gerado_em", "valido_para", "modelo_fonte"),
    )
    op.create_table(
        "previsao_nivel",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("estacao_id", sa.Integer(), nullable=False),
        sa.Column("modelo_id", sa.Integer(), nullable=False),
        sa.Column(
            "gerado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valido_para", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nivel_m", sa.Double(), nullable=False),
        sa.Column("incerteza_m", sa.Double(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["estacao_id"],
            ["estacao.id"],
        ),
        sa.ForeignKeyConstraint(
            ["modelo_id"],
            ["modelo.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("previsao_nivel")
    op.drop_table("previsao_chuva")
    op.drop_table("modelo")
    op.drop_table("limiar")
    op.drop_index("idx_leitura_consulta", table_name="leitura")
    op.drop_table("leitura")
    op.drop_table("inscricao")
    op.drop_table("alerta")
    op.drop_table("log_coleta")
    op.drop_table("estacao")
    op.drop_table("ocorrencia")
    op.drop_table("fonte")
