"""Montagem das variaveis do modelo (docs/especificacao-completa.md, secao 9.2).

REGRA DE OURO, sem excecao: toda variavel na hora `t` usa so dado ate `t`. Janelas de chuva
terminam em `t`; diferencas olham para tras; o alvo (futuro) e construido a parte e nunca entra
em X. Ha teste que prova isso cortando a serie em `t` e comparando.

Cada hora sem cobertura vira NaN (nunca zero). Linhas com NaN nao entram no treino.
"""

import numpy as np
import pandas as pd

HORIZONTES_H = (1, 3, 6, 12, 24)
JANELAS_CHUVA_H = (1, 3, 6, 12, 24, 48, 72, 168)
ALVO = "DCSC-00043"
# ponto de chuva -> rotulo curto usado nos nomes das variaveis
PONTOS_CHUVA = {
    "DCSC-00043": "local",
    "DCSC-00037": "emma",
    "DCSC-00021": "boiteux",
    "DCSC-00015": "witmarsum",
    "DCSC-00036": "vitor",
}
NIVEL_VIZINHOS = {"DCSC-00021": "boiteux", "DCSC-00020": "ibirama"}
MIN_COBERTURA_LONGA = 0.9  # janelas de 48 h ou mais toleram 10% de falha (reescaladas)


def chuva_acumulada(chuva_h: pd.Series, janela: int) -> pd.Series:
    """Soma da chuva nas ultimas `janela` horas ate t. Janelas longas toleram pouca falha."""
    if janela < 48:
        return chuva_h.rolling(janela, min_periods=janela).sum()
    minimo = int(np.ceil(janela * MIN_COBERTURA_LONGA))
    soma = chuva_h.rolling(janela, min_periods=minimo).sum()
    n = chuva_h.rolling(janela, min_periods=minimo).count()
    return soma * (janela / n)  # reescala pela cobertura


def montar_features(
    chuva: dict[str, pd.Series], nivel: dict[str, pd.Series], alvo: str = ALVO
) -> pd.DataFrame:
    """Uma linha por hora `t`. `chuva` e `nivel` sao series horarias (UTC) por codigo de estacao."""
    cols: dict[str, pd.Series] = {}
    n_alvo = nivel[alvo]
    cols["nivel_m"] = n_alvo
    cols["taxa_1h_cm"] = n_alvo.diff(1) * 100
    cols["taxa_3h_cm_h"] = n_alvo.diff(3) * 100 / 3
    cols["aceleracao_cm"] = cols["taxa_1h_cm"].diff(1)

    for cod, rotulo in NIVEL_VIZINHOS.items():
        if cod in nivel:
            cols[f"nivel_{rotulo}_m"] = nivel[cod]
            cols[f"taxa_{rotulo}_1h_cm"] = nivel[cod].diff(1) * 100

    for cod, rotulo in PONTOS_CHUVA.items():
        if cod in chuva:
            for j in JANELAS_CHUVA_H:
                cols[f"chuva_{rotulo}_{j}h"] = chuva_acumulada(chuva[cod], j)

    # interacoes que testam a hipotese do coordenador e o remanso (secao 1.2)
    if "chuva_emma_6h" in cols and "chuva_boiteux_6h" in cols:
        cols["emma_x_boiteux_6h"] = cols["chuva_emma_6h"] * cols["chuva_boiteux_6h"]
    if "nivel_ibirama_m" in cols and "chuva_local_3h" in cols:
        cols["ibirama_x_chuva_local_3h"] = cols["nivel_ibirama_m"] * cols["chuva_local_3h"]

    df = pd.DataFrame(cols)
    hora = df.index.hour
    df["hora_sen"] = np.sin(2 * np.pi * hora / 24)
    df["hora_cos"] = np.cos(2 * np.pi * hora / 24)
    return df


def alvo_deslocado(nivel_alvo: pd.Series, horizonte_h: int) -> pd.Series:
    """Variacao do nivel daqui a `horizonte_h` horas, em cm: nivel(t+h) - nivel(t).

    E o unico lugar que olha para o futuro, e so serve de resposta no treino.
    """
    return (nivel_alvo.shift(-horizonte_h) - nivel_alvo) * 100
