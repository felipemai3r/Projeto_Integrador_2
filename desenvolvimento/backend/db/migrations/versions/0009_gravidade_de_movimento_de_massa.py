"""gravidade das ocorrencias de movimento de massa

Revision ID: 0009
Revises: 0008

O mapa passa a receber, alem de alagamentos, deslizamentos, quedas de pedras e sinais de
movimentacao de terra (grupo 1.1.3 da COBRADE). Esses registros trazem a gravidade
(baixa, media, alta), que a moderacao pode corrigir; nos alagamentos ela fica nula, porque
o proprio tipo ja diz a gravidade. So colunas novas e anulaveis: nada muda nas linhas atuais.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ocorrencia", sa.Column("gravidade", sa.Text(), nullable=True))
    op.add_column(
        "moderacao", sa.Column("gravidade_anterior", sa.Text(), nullable=True)
    )
    op.add_column("moderacao", sa.Column("gravidade_nova", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("moderacao", "gravidade_nova")
    op.drop_column("moderacao", "gravidade_anterior")
    op.drop_column("ocorrencia", "gravidade")
