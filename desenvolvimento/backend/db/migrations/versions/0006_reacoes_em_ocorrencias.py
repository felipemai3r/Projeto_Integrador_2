"""curtir e denunciar ocorrencias

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reacao_ocorrencia",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("ocorrencia_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("chave_hash", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ocorrencia_id"], ["ocorrencia.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ocorrencia_id", "tipo", "chave_hash", name="uq_reacao_por_aparelho"
        ),
    )


def downgrade() -> None:
    op.drop_table("reacao_ocorrencia")
