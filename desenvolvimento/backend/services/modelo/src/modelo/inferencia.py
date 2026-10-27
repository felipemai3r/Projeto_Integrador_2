"""Aplicacao de um modelo publicado a uma linha de variaveis (CDU09).

Funcoes puras, sem banco. Quem decide se o modelo EXISTE (RN07) e a camada acima; aqui se
calcula, sinaliza extrapolacao e monta cenarios hipoteticos (CDU03).
"""

import pandas as pd

from modelo.features import JANELAS_CHUVA_H, PONTOS_CHUVA

ROTULO_DE_CODIGO = PONTOS_CHUVA
MARGEM_EXTRAPOLACAO = 0.0  # qualquer valor fora do intervalo visto no treino conta
JANELA_IMPUTACAO_H = max(JANELAS_CHUVA_H)  # so as ultimas 168 h importam para as variaveis
MAX_HORAS_IMPUTADAS = 24  # acima disso o ponto fica como esta: sem estimativa
MIN_VIZINHOS_IMPUTACAO = 2  # outros pontos com dado na mesma hora para poder estimar


def imputar_chuva(
    chuva: dict[str, pd.Series],
    janela_h: int = JANELA_IMPUTACAO_H,
    max_horas: int = MAX_HORAS_IMPUTADAS,
    min_vizinhos: int = MIN_VIZINHOS_IMPUTACAO,
) -> tuple[dict[str, pd.Series], dict[str, pd.DatetimeIndex]]:
    """Preenche horas de chuva sem leitura com a media dos OUTROS pontos de chuva.

    SOMENTE PARA INFERENCIA. No treino a regra e outra e continua valendo: hora sem cobertura
    e NaN, nunca zero e nunca inventada (modelo/dados.py e features.py), para o modelo nao
    aprender com chuva que ninguem mediu. Aqui, na hora de estimar o nivel agora, uma falha da
    fonte (ex.: um ponto sem dados por 14 h) desligaria a previsao inteira por dias; entao se
    usa uma estimativa grosseira, e quem chama DEVE avisar o usuario (ver `chuva_estimada`).

    Regras:
    - olha so as ultimas `janela_h` horas do indice comum (a janela mais longa das variaveis);
    - uma hora so e preenchida se ao menos `min_vizinhos` outros pontos tem dado nela;
    - se o ponto precisaria de mais de `max_horas` horas preenchidas, nao se mexe nele;
    - nivel nao passa por aqui, e nunca e imputado.

    Nao altera as series recebidas. Devolve as series (as nao alteradas voltam iguais) e, por
    ponto, as horas que foram preenchidas.
    """
    novas = dict(chuva)
    usadas = {c: v for c, v in chuva.items() if not v.empty}
    if len(usadas) <= min_vizinhos:
        return novas, {}
    ini = min(v.index.min() for v in usadas.values())
    fim = max(v.index.max() for v in usadas.values())
    quadro = pd.DataFrame(usadas).reindex(pd.date_range(ini, fim, freq="1h"))
    cauda = quadro.iloc[-janela_h:]
    preenchidas: dict[str, pd.DatetimeIndex] = {}
    for cod in usadas:
        sem_dado = cauda[cod].isna()
        if not sem_dado.any() or sem_dado.sum() > max_horas:
            continue
        outros = cauda.drop(columns=cod)
        pode = sem_dado & (outros.notna().sum(axis=1) >= min_vizinhos)
        if not pode.any():
            continue
        serie = quadro[cod].copy()
        serie.loc[pode[pode].index] = outros.mean(axis=1)[pode]
        novas[cod] = serie
        preenchidas[cod] = pode[pode].index
    return novas, preenchidas


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
