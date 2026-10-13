"""tabela de correlacao

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "correlacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "calculado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("estacao_alvo_id", sa.Integer(), nullable=False),
        sa.Column("ponto_id", sa.Integer(), nullable=False),
        sa.Column("explicativa", sa.Text(), nullable=False),
        sa.Column("janela_chuva_h", sa.Integer(), nullable=False),
        sa.Column("melhor_defasagem_h", sa.Integer(), nullable=False),
        sa.Column("r", sa.Double(), nullable=False),
        sa.Column("ic_inf", sa.Double(), nullable=True),
        sa.Column("ic_sup", sa.Double(), nullable=True),
        sa.Column("p_valor", sa.Double(), nullable=True),
        sa.Column("horas_validas", sa.Integer(), nullable=False),
        sa.Column("curva", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metodo", sa.Text(), nullable=False),
        sa.Column("periodo_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("periodo_fim", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["estacao_alvo_id"],
            ["estacao.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ponto_id"],
            ["estacao.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("correlacao")
