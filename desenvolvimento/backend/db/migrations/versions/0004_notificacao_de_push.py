"""notificacao de push

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notificacao",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("alerta_id", sa.BigInteger(), nullable=False),
        sa.Column("inscricao_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column(
            "enviada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["alerta_id"],
            ["alerta.id"],
        ),
        sa.ForeignKeyConstraint(
            ["inscricao_id"],
            ["inscricao.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notificacao")
