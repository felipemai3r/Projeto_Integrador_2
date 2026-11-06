"""Aplicacao de um modelo publicado a uma linha de variaveis (CDU09).

Funcoes puras, sem banco. Quem decide se o modelo EXISTE (RN07) e a camada acima; aqui se
calcula, sinaliza extrapolacao e monta cenarios hipoteticos (CDU03).
"""

import pandas as pd

from modelo.features import JANELAS_CHUVA_H, PONTOS_CHUVA, pontos_chuva
from modelo.treino import regime_da_linha

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
    """Variacao prevista do nivel (cm) no horizonte do modelo.

    Modelo novo (`aceita_nan`): coluna que a linha nao tem vira NaN (nunca zero), que o modelo
    sabe tratar. Modelo antigo (Ridge): coluna ausente levanta KeyError, como sempre; a camada
    acima so chega aqui com todas as colunas preenchidas.
    """
    colunas = artefato["colunas"]
    amostra = linha.reindex(colunas) if artefato.get("aceita_nan") else linha[colunas]
    return float(artefato["pipeline"].predict(amostra.to_frame().T.astype(float))[0])


def obrigatorias_do_artefato(artefato: dict) -> list[str] | None:
    """Colunas obrigatorias de um modelo que aceita NaN, ou None para o modelo antigo (Ridge),
    que exige todas as `colunas`."""
    if not artefato.get("aceita_nan"):
        return None
    return list(artefato.get("colunas_obrigatorias", []))


def colunas_exigidas(artefato: dict) -> list[str]:
    """Colunas que precisam estar preenchidas na linha para o modelo poder estimar.

    Modelo novo (`aceita_nan`): so as obrigatorias, mais o nivel (a base da previsao); as demais
    podem ser NaN. Modelo antigo (sem o campo): todas as `colunas`.
    """
    obrigatorias = obrigatorias_do_artefato(artefato)
    if obrigatorias is None:
        return list(artefato["colunas"])
    return list(dict.fromkeys([*obrigatorias, "nivel_m"]))


def colunas_faltando(artefato: dict, linha: pd.Series) -> list[str]:
    """Colunas que o modelo exige e a linha nao tem (ausentes ou NaN).

    Cada modelo so olha as proprias colunas: um modelo que nao usa uma serra nunca falha por
    causa dela; um modelo antigo treinado com ela fica sem estimativa se ela estiver sem dado,
    em vez de errar ou inventar. O modelo novo so exige as obrigatorias (`colunas_exigidas`).
    """
    return [c for c in colunas_exigidas(artefato) if c not in linha.index or pd.isna(linha[c])]


def extrapola(artefato: dict, linha: pd.Series) -> list[str]:
    """Variaveis fora da faixa vista no treino. Lista vazia = dentro do que o modelo conhece.

    Variavel sem valor (NaN) nao tem como extrapolar: fica de fora.
    """
    fora = []
    for coluna, (minimo, maximo) in artefato.get("faixa_treino", {}).items():
        v = linha.get(coluna)
        if v is None or pd.isna(v):
            continue
        if v < minimo - MARGEM_EXTRAPOLACAO or v > maximo + MARGEM_EXTRAPOLACAO:
            fora.append(coluna)
    return fora


def intervalo_cm(
    artefato: dict, linha: pd.Series, metadados: dict | None = None
) -> tuple[float, float] | None:
    """Limites (lo, hi) em cm a somar a variacao prevista, ou None se o modelo nao os tem.

    Vem de `intervalo_por_regime` (no artefato; senao nos metadados do registro) e usa o regime
    da linha, o mesmo da validacao (`treino.regime_da_linha`). None = modelo antigo: quem chama
    usa +-1,96 desvios.
    """
    por_regime = artefato.get("intervalo_por_regime") or (metadados or {}).get(
        "intervalo_por_regime"
    )
    if not por_regime:
        return None
    limites = por_regime.get(regime_da_linha(linha, artefato["colunas"]))
    return (float(limites[0]), float(limites[1])) if limites else None


def aplicar_cenario(
    linha: pd.Series,
    chuva_mm_por_ponto: dict[str, float],
    janela_h: int,
    alvo: str | None = None,
) -> pd.Series:
    """Cenario: "e se nas ultimas `janela_h` horas tivesse chovido X mm em cada ponto?".

    Intensidade uniforme na janela. Janelas de chuva menores ou iguais a `janela_h` recebem a
    fracao proporcional; as maiores recebem pelo menos o total do cenario (nunca menos do que
    ja choveu de fato). Interacoes sao recalculadas. O nivel e a tendencia ficam como estao.
    Com `alvo`, so os pontos de chuva desse alvo (`ConfigAlvo.pontos_chuva`) sao aplicados.
    """
    nova = linha.copy()
    do_alvo = pontos_chuva(alvo) if alvo is not None else ROTULO_DE_CODIGO
    for codigo, mm in chuva_mm_por_ponto.items():
        rotulo = do_alvo.get(codigo)
        if rotulo is None:
            continue
        for w in JANELAS_CHUVA_H:
            col = f"chuva_{rotulo}_{w}h"
            if col not in nova.index:
                continue
            valor = mm * min(w, janela_h) / janela_h
            # janela maior que a do cenario: nunca menos do que ja choveu. Sem leitura (NaN), nao
            # ha "ja choveu" a preservar e vale o cenario (max() com NaN devolveria NaN)
            atual = nova[col]
            nova[col] = valor if w <= janela_h or pd.isna(atual) else max(float(atual), valor)
    if {"chuva_emma_6h", "chuva_boiteux_6h", "emma_x_boiteux_6h"} <= set(nova.index):
        nova["emma_x_boiteux_6h"] = nova["chuva_emma_6h"] * nova["chuva_boiteux_6h"]
    if {"nivel_ibirama_m", "chuva_local_3h", "ibirama_x_chuva_local_3h"} <= set(nova.index):
        nova["ibirama_x_chuva_local_3h"] = nova["nivel_ibirama_m"] * nova["chuva_local_3h"]
    return nova
