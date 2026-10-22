"""avisos por e-mail

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inscricao_email",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("estacao_id", sa.BigInteger(), nullable=True),
        sa.Column("faixa_minima", sa.Text(), nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmada_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["estacao_id"], ["estacao.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "notificacao_email",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("alerta_id", sa.BigInteger(), nullable=False),
        sa.Column("inscricao_email_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column(
            "enviada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["alerta_id"], ["alerta.id"]),
        sa.ForeignKeyConstraint(
            ["inscricao_email_id"], ["inscricao_email.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notificacao_email")
    op.drop_table("inscricao_email")
