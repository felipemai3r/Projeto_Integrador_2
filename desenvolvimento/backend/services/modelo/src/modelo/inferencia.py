"""Aplicacao de um modelo publicado a uma linha de variaveis (CDU09).

Funcoes puras, sem banco. Quem decide se o modelo EXISTE (RN07) e a camada acima; aqui se
calcula, sinaliza extrapolacao e monta cenarios hipoteticos (CDU03).
"""

import pandas as pd

from modelo.features import JANELAS_CHUVA_H, PONTOS_CHUVA

ROTULO_DE_CODIGO = PONTOS_CHUVA
MARGEM_EXTRAPOLACAO = 0.0  # qualquer valor fora do intervalo visto no treino conta


def prever_variacao_cm(artefato: dict, linha: pd.Series) -> float:
    """Variacao prevista do nivel (cm) no horizonte do modelo."""
    X = linha[artefato["colunas"]].to_frame().T.astype(float)
    return float(artefato["pipeline"].predict(X)[0])


def extrapola(artefato: dict, linha: pd.Series) -> list[str]:
    """Variaveis fora da faixa vista no treino. Lista vazia = dentro do que o modelo conhece."""
    fora = []
    for coluna, (minimo, maximo) in artefato.get("faixa_treino", {}).items():
        v = linha.get(coluna)
        if v is not None and (v < minimo - MARGEM_EXTRAPOLACAO or v > maximo + MARGEM_EXTRAPOLACAO):
            fora.append(coluna)
    return fora


def aplicar_cenario(
    linha: pd.Series, chuva_mm_por_ponto: dict[str, float], janela_h: int
) -> pd.Series:
    """Cenario: "e se nas ultimas `janela_h` horas tivesse chovido X mm em cada ponto?".

    Intensidade uniforme na janela. Janelas de chuva menores ou iguais a `janela_h` recebem a
    fracao proporcional; as maiores recebem pelo menos o total do cenario (nunca menos do que
    ja choveu de fato). Interacoes sao recalculadas. O nivel e a tendencia ficam como estao.
    """
    nova = linha.copy()
    for codigo, mm in chuva_mm_por_ponto.items():
        rotulo = ROTULO_DE_CODIGO.get(codigo)
        if rotulo is None:
            continue
        for w in JANELAS_CHUVA_H:
            col = f"chuva_{rotulo}_{w}h"
            if col not in nova.index:
                continue
            valor = mm * min(w, janela_h) / janela_h
            nova[col] = valor if w <= janela_h else max(float(nova[col]), valor)
    if {"chuva_emma_6h", "chuva_boiteux_6h", "emma_x_boiteux_6h"} <= set(nova.index):
        nova["emma_x_boiteux_6h"] = nova["chuva_emma_6h"] * nova["chuva_boiteux_6h"]
    if {"nivel_ibirama_m", "chuva_local_3h", "ibirama_x_chuva_local_3h"} <= set(nova.index):
        nova["ibirama_x_chuva_local_3h"] = nova["nivel_ibirama_m"] * nova["chuva_local_3h"]
    return nova
