"""escala de risco da Defesa Civil de SC (normal, atencao, alerta, alerta_alto, extremo)

Revision ID: 0007
Revises: 0006

Antes: normal < observacao < atencao < alerta. Depois: normal < atencao < alerta < alerta_alto
< extremo. Os valores guardados sobem um degrau (observacao -> atencao, atencao -> alerta,
alerta -> alerta_alto), para que cada limiar e cada inscricao continuem significando o mesmo.
`extremo` e novo e ainda nao tem limiar cadastrado.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# (tabela, coluna) de todo campo de texto que guarda uma faixa
COLUNAS = [
    ("limiar", "faixa"),
    ("alerta", "faixa_anterior"),
    ("alerta", "faixa_nova"),
    ("alerta", "severidade"),
    ("inscricao", "faixa_minima"),
    ("inscricao_email", "faixa_minima"),
]

SOBE = {"observacao": "atencao", "atencao": "alerta", "alerta": "alerta_alto"}
# extremo nao existia: colapsa em alerta, o topo da escala antiga
DESCE = {
    "atencao": "observacao",
    "alerta": "atencao",
    "alerta_alto": "alerta",
    "extremo": "alerta",
}


def _remapear(mapa: dict[str, str]) -> None:
    # Um UPDATE por coluna com CASE: os degraus nao se encadeiam (sem passar duas vezes na linha)
    casos = " ".join(f"WHEN '{de}' THEN '{para}'" for de, para in mapa.items())
    antigos = ", ".join(f"'{de}'" for de in mapa)
    for tabela, coluna in COLUNAS:
        op.execute(
            f"UPDATE {tabela} SET {coluna} = CASE {coluna} {casos} ELSE {coluna} END "
            f"WHERE {coluna} IN ({antigos})"
        )


def upgrade() -> None:
    _remapear(SOBE)


def downgrade() -> None:
    # Limiar extremo nao tem equivalente antigo e colidiria com alerta_alto -> alerta
    op.execute("DELETE FROM limiar WHERE faixa = 'extremo'")
    _remapear(DESCE)
