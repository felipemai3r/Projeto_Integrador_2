"""usuario e moderacao

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("papel", sa.Text(), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "moderacao",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("ocorrencia_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("status_anterior", sa.Text(), nullable=False),
        sa.Column("status_novo", sa.Text(), nullable=False),
        sa.Column("tipo_anterior", sa.Text(), nullable=False),
        sa.Column("tipo_novo", sa.Text(), nullable=False),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column(
            "em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ocorrencia_id"],
            ["ocorrencia.id"],
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("moderacao")
    op.drop_table("usuario")
