"""preferencias pendentes na inscricao por e-mail

Revision ID: 0008
Revises: 0007

Quem ja confirmou o e-mail nao pode ser desligado por um novo POST de terceiro. O pedido de
mudanca de preferencias passa a ficar nas colunas *_pendente, com token proprio, e so vale
depois do clique no link. So colunas novas e anulaveis: linhas existentes ficam como estao
(sem pedido pendente) e a inscricao confirmada continua recebendo.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inscricao_email", sa.Column("token_hash_pendente", sa.Text(), nullable=True)
    )
    op.add_column(
        "inscricao_email",
        sa.Column("estacao_id_pendente", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "inscricao_email", sa.Column("faixa_minima_pendente", sa.Text(), nullable=True)
    )
    op.add_column(
        "inscricao_email",
        sa.Column("pendente_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_inscricao_email_token_hash_pendente",
        "inscricao_email",
        ["token_hash_pendente"],
    )
    op.create_foreign_key(
        "fk_inscricao_email_estacao_pendente",
        "inscricao_email",
        "estacao",
        ["estacao_id_pendente"],
        ["id"],
    )


def downgrade() -> None:
    # Pedido pendente e descartado: nao ha onde guarda-lo no esquema antigo. As preferencias
    # vigentes (faixa_minima, estacao_id, confirmada_em) nao sao tocadas.
    op.drop_constraint(
        "fk_inscricao_email_estacao_pendente", "inscricao_email", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_inscricao_email_token_hash_pendente", "inscricao_email", type_="unique"
    )
    op.drop_column("inscricao_email", "pendente_em")
    op.drop_column("inscricao_email", "faixa_minima_pendente")
    op.drop_column("inscricao_email", "estacao_id_pendente")
    op.drop_column("inscricao_email", "token_hash_pendente")
