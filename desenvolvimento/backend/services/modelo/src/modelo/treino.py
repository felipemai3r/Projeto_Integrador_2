"""Treino, validacao honesta e criterio de publicacao do modelo (CDU12, RN07, secao 9.4).

- Modelo: HistGradientBoostingRegressor (perda absoluta, sem early stopping, deterministico).
  Aceita NaN: uma variavel sem leitura na hora nao derruba a linha (ADR 0006).
- Alvo: variacao do nivel em `h` horas (cm). Prever a variacao, nao o nivel, torna a
  persistencia o baseline natural (variacao zero).
- Validacao: walk-forward em ordem temporal, 5 dobras, com `gap` de `h` horas entre treino e
  teste para o alvo do treino nao enxergar o futuro do teste.
- Baselines obrigatorios: persistencia (variacao 0) e extrapolacao linear da tendencia atual.
- Publicacao (RN07): so publica se o modelo vencer a persistencia por margem minima E houver ao
  menos 60 dias de dado util. Caso contrario a previsao fica INDISPONIVEL, com o motivo.
- Intervalo: quantis empiricos dos residuos fora da amostra das 5 dobras, por regime de chuva
  (seco, chuva, chuva forte), com o nivel do quantil calibrado para cobrir >= 95% (ADR 0006).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import TimeSeriesSplit


def cm_br(valor: float | None) -> str:
    """Numero no formato brasileiro, com duas casas: 45,20."""
    return f"{valor or 0:.2f}".replace(".", ",")


DIAS_MINIMOS = 60  # RN07
MARGEM_SOBRE_PERSISTENCIA = 0.05  # o modelo precisa errar pelo menos 5% menos que a persistencia
N_DOBRAS = 5
# O modelo aceita NaN, mas estas tres sao sempre exigidas: sem o nivel e as taxas recentes nao
# ha previsao (e a tendencia, baseline da validacao, usa `taxa_3h_cm_h`). Linhas sem elas saem.
COLUNAS_OBRIGATORIAS = ("nivel_m", "taxa_1h_cm", "taxa_3h_cm_h")
# O HistGradientBoosting quebra com coluna totalmente vazia, e uma coluna quase vazia so
# decora ruido: em cada ajuste (dobra ou final) sai quem tem menos que isso no treino.
MIN_NAO_NULOS = 50

# Intervalo por regime de chuva (ADR 0006). `m` = maior chuva de 6 h entre os pontos do modelo.
REGIMES = ("seco", "chuva", "chuva_forte")
LIMITE_CHUVA_MM = 1.0  # m < 1 mm: seco
LIMITE_CHUVA_FORTE_MM = 10.0  # m >= 10 mm (ou chuva toda desconhecida): chuva forte
# Candidatos ao nivel dos quantis (alfa e 1 - alfa). A chuva futura nao e conhecida, entao em
# 12 e 24 h os quantis 2,5/97,5 cobrem menos de 95%: sobe-se o nivel ate a cobertura servir.
ALFAS_INTERVALO = (0.025, 0.015, 0.01, 0.005, 0.0025)  # candidatos para 95% de confianca
COBERTURA_ALVO = 0.95
# Nivel de confianca do intervalo por horizonte. Em 12 e 24 h a chuva que ainda vai cair domina o
# erro e o intervalo de 95% fica largo demais para orientar (medido: 152 cm de largura em 24 h
# mesmo com tempo seco); 80% da 42 cm e e o nivel usual em boletins de horizonte longo. A tela
# mostra sempre o nivel usado, e a calibracao garante a cobertura prometida (ADR 0006).
CONFIANCA_POR_HORIZONTE = {1: 0.95, 3: 0.95, 6: 0.95, 12: 0.80, 24: 0.80}


def confianca_do_horizonte(horizonte_h: int) -> float:
    return CONFIANCA_POR_HORIZONTE.get(horizonte_h, COBERTURA_ALVO)


def alfas_candidatos(confianca: float) -> tuple[float, ...]:
    """Do alfa nominal ((1 - confianca) / 2) para caudas cada vez mais largas."""
    a = (1 - confianca) / 2
    return tuple(round(a * f, 6) for f in (1.0, 0.6, 0.4, 0.2, 0.1))


FRACAO_CALIBRACAO = 0.6  # primeiros 60% dos residuos calibram; os ultimos 40% medem a cobertura
MIN_RESIDUOS_REGIME = 30  # regime com menos residuos que isso usa os quantis de todos


@dataclass
class Resultado:
    horizonte_h: int
    amostras: int
    dias_uteis: float
    rmse_cm: float | None = None
    mae_cm: float | None = None
    rmse_persistencia_cm: float | None = None
    rmse_tendencia_cm: float | None = None
    desvio_residual_cm: float | None = None  # mantido por compatibilidade (artefato antigo)
    publicar: bool = False
    motivo: str = ""
    colunas: list[str] = field(default_factory=list)
    pipeline: object | None = None  # modelo final, ajustado em todos os dados
    faixa_treino: dict[str, tuple[float, float]] = field(default_factory=dict)
    # intervalo = previsto + [lo, hi] (cm) do regime da linha; residuo = real - previsto
    intervalo_por_regime: dict[str, list[float]] = field(default_factory=dict)
    alfa_intervalo: float | None = None
    cobertura_validacao: float | None = None  # cobertura nos ultimos 40% dos residuos
    confianca: float = COBERTURA_ALVO  # nivel de confianca prometido pelo intervalo
    colunas_obrigatorias: list[str] = field(default_factory=list)
    aceita_nan: bool = True  # marca o modelo novo: a inferencia tolera NaN fora das obrigatorias


def novo_pipeline(horizonte_h: int = 1) -> object:
    """Gradient boosting com perda absoluta: PONTO UNICO de construcao do estimador.

    Sem early stopping (o `auto` ligaria sozinho com mais de 10 mil linhas e tiraria uma fatia
    do treino ao acaso, quebrando a ordem temporal) e com semente fixa: mesmo dado, mesmo modelo.
    `horizonte_h` nao muda nada hoje; fica na assinatura porque o validador sempre o passa.
    """
    return HistGradientBoostingRegressor(
        loss="absolute_error",
        max_iter=600,
        learning_rate=0.04,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=2.0,
        early_stopping=False,
        random_state=0,
    )


def _rmse(erro: np.ndarray) -> float:
    return float(np.sqrt(np.mean(erro**2)))


def colunas_obrigatorias_de(colunas: Iterable[str]) -> list[str]:
    """As colunas obrigatorias que existem em `colunas` (na ordem de COLUNAS_OBRIGATORIAS)."""
    existentes = set(colunas)
    return [c for c in COLUNAS_OBRIGATORIAS if c in existentes]


def preparar(X: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Mantem as linhas com alvo e com as colunas obrigatorias, em ordem temporal.

    As demais colunas podem ser NaN (o modelo aceita): hora sem cobertura e desconhecida, nunca
    zero. Uma obrigatoria que nem existe em X e ignorada (so ha X sinteticos assim).
    """
    obrigatorias = colunas_obrigatorias_de(X.columns)
    base = X.assign(__y=y).dropna(subset=[*obrigatorias, "__y"]).sort_index()
    return base.drop(columns="__y"), base["__y"]


def colunas_usaveis(X: pd.DataFrame) -> list[str]:
    """Colunas com dado suficiente para ajustar (>= MIN_NAO_NULOS valores nao nulos).

    As obrigatorias nunca saem: elas nao tem NaN e so ficam abaixo do minimo em treino minusculo.
    """
    obrigatorias = set(colunas_obrigatorias_de(X.columns))
    nao_nulos = X.notna().sum()
    return [c for c in X.columns if c in obrigatorias or nao_nulos[c] >= MIN_NAO_NULOS]


def colunas_chuva_6h(colunas: Iterable[str]) -> list[str]:
    """Colunas `chuva_<ponto>_6h`: a chuva de 6 h de cada ponto, que define o regime."""
    return [c for c in colunas if re.fullmatch(r"chuva_.+_6h", c)]


def regime_chuva(chuva_6h: np.ndarray) -> np.ndarray:
    """Regime de cada linha a partir das chuvas de 6 h dos pontos (uma coluna por ponto).

    m = maior chuva entre os pontos: `seco` (m < 1 mm), `chuva` (1 <= m < 10) ou `chuva_forte`
    (m >= 10). Sem nenhuma chuva conhecida (tudo NaN, ou nenhum ponto) vale `chuva_forte`:
    sem saber se chove, o intervalo largo e o lado seguro.
    """
    n = len(chuva_6h)
    if chuva_6h.size == 0:
        return np.full(n, "chuva_forte", dtype=object)
    valores = np.asarray(chuva_6h, dtype=float)
    desconhecida = np.isnan(valores).all(axis=1)
    m = np.max(np.where(np.isnan(valores), -np.inf, valores), axis=1)
    regime = np.where(m >= LIMITE_CHUVA_FORTE_MM, "chuva_forte", "chuva")
    regime = np.where(m < LIMITE_CHUVA_MM, "seco", regime)
    return np.where(desconhecida, "chuva_forte", regime).astype(object)


def regime_da_linha(linha: pd.Series, colunas: Iterable[str]) -> str:
    """Regime de UMA linha de variaveis, olhando so as colunas de chuva de 6 h do modelo."""
    cols = colunas_chuva_6h(colunas)
    valores = linha.reindex(cols).to_numpy(dtype=float).reshape(1, -1)
    return str(regime_chuva(valores)[0])


def _limites_por_regime(
    res: np.ndarray, regimes: np.ndarray, alfa: float
) -> dict[str, tuple[float, float]]:
    """Quantis alfa e 1 - alfa dos residuos de cada regime; regime ralo usa os de todos."""
    quantis = [alfa, 1 - alfa]
    geral = np.quantile(res, quantis)
    limites = {}
    for regime in REGIMES:
        do_regime = res[regimes == regime]
        q = np.quantile(do_regime, quantis) if len(do_regime) >= MIN_RESIDUOS_REGIME else geral
        limites[regime] = (float(q[0]), float(q[1]))
    return limites


def _cobertura(
    res: np.ndarray, regimes: np.ndarray, limites: dict[str, tuple[float, float]]
) -> float:
    lo = np.array([limites[g][0] for g in regimes])
    hi = np.array([limites[g][1] for g in regimes])
    return float(np.mean((res >= lo) & (res <= hi)))


def calibrar_intervalo(
    res: np.ndarray, regimes: np.ndarray, confianca: float = COBERTURA_ALVO
) -> tuple[dict[str, list[float]], float, float]:
    """Intervalo por regime a partir dos residuos (real - previsto) em ORDEM TEMPORAL.

    Para cada alfa candidato, calibra os quantis por regime nos primeiros 60% dos residuos e mede
    a cobertura nos ultimos 40%; fica o primeiro alfa com cobertura >= `confianca` (se nenhum, o
    menor).
    Com o alfa escolhido, os quantis sao recalculados com TODOS os residuos. Devolve
    (`{regime: [lo_cm, hi_cm]}`, alfa, cobertura medida nos ultimos 40%).
    """
    corte = int(len(res) * FRACAO_CALIBRACAO)
    cal, val = (res[:corte], regimes[:corte]), (res[corte:], regimes[corte:])
    candidatos = alfas_candidatos(confianca)
    alfa, cobertura = candidatos[-1], 0.0
    for candidato in candidatos:
        cobertura = _cobertura(*val, _limites_por_regime(*cal, candidato))
        alfa = candidato
        if cobertura >= confianca:
            break
    limites = _limites_por_regime(res, regimes, alfa)
    return {g: [round(lo, 2), round(hi, 2)] for g, (lo, hi) in limites.items()}, alfa, cobertura


def avaliar_horizonte(X: pd.DataFrame, y: pd.Series, horizonte_h: int) -> Resultado:
    Xc, yc = preparar(X, y)
    dias = len(Xc) / 24
    r = Resultado(horizonte_h=horizonte_h, amostras=len(Xc), dias_uteis=round(dias, 1))
    r.colunas = list(Xc.columns)
    r.colunas_obrigatorias = colunas_obrigatorias_de(Xc.columns)
    if len(Xc) < N_DOBRAS * 48:
        r.motivo = f"Poucos dados para validar ({len(Xc)} horas completas)."
        return r

    erros_modelo, erros_persist, erros_tend, posicoes_teste = [], [], [], []
    cv = TimeSeriesSplit(n_splits=N_DOBRAS, gap=horizonte_h)
    for treino, teste in cv.split(Xc):
        # cada dobra descarta as colunas ralas DO SEU treino (o teste nao entra na escolha)
        cols = colunas_usaveis(Xc.iloc[treino])
        modelo = novo_pipeline(horizonte_h)
        modelo.fit(Xc.iloc[treino][cols], yc.iloc[treino])  # type: ignore[attr-defined]
        pred = modelo.predict(Xc.iloc[teste][cols])  # type: ignore[attr-defined]
        real = yc.iloc[teste].to_numpy()
        erros_modelo.append(pred - real)
        erros_persist.append(0.0 - real)
        tendencia = Xc.iloc[teste]["taxa_3h_cm_h"].to_numpy() * horizonte_h
        erros_tend.append(tendencia - real)
        posicoes_teste.append(teste)

    em, ep, et = (np.concatenate(e) for e in (erros_modelo, erros_persist, erros_tend))
    r.rmse_cm, r.mae_cm = _rmse(em), float(np.mean(np.abs(em)))
    r.rmse_persistencia_cm, r.rmse_tendencia_cm = _rmse(ep), _rmse(et)
    r.desvio_residual_cm = float(np.std(em))

    # o modelo final usa as colunas com dado suficiente em TODO o treino; e delas que se tira o
    # regime de chuva dos residuos (as dobras de teste sao crescentes: res fica em ordem temporal)
    r.colunas = colunas_usaveis(Xc)
    regimes = regime_chuva(
        Xc.iloc[np.concatenate(posicoes_teste)][colunas_chuva_6h(r.colunas)].to_numpy(dtype=float)
    )
    r.confianca = confianca_do_horizonte(horizonte_h)
    r.intervalo_por_regime, r.alfa_intervalo, r.cobertura_validacao = calibrar_intervalo(
        -em, regimes, r.confianca
    )

    ganha_persistencia = r.rmse_cm < r.rmse_persistencia_cm * (1 - MARGEM_SOBRE_PERSISTENCIA)
    if dias < DIAS_MINIMOS:
        r.motivo = (
            f"Só há {dias:.0f} dias de dados completos; o mínimo para publicar é {DIAS_MINIMOS}."
        )
    elif not ganha_persistencia:
        r.motivo = (
            f"O modelo não superou a persistência (erro de {cm_br(r.rmse_cm)} cm contra "
            f"{cm_br(r.rmse_persistencia_cm)} cm de quem apenas repete o nível atual)."
        )
    else:
        r.publicar = True
        r.motivo = "Superou a persistência na validação."
    r.faixa_treino = {c: (float(Xc[c].min()), float(Xc[c].max())) for c in r.colunas}
    final = novo_pipeline(horizonte_h)
    final.fit(Xc[r.colunas], yc)  # type: ignore[attr-defined]
    r.pipeline = final
    return r
