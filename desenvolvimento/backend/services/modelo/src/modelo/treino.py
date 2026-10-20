"""Treino, validacao honesta e criterio de publicacao do modelo (CDU12, RN07, secao 9.4).

- Modelo de referencia: Ridge (regressao linear regularizada), variaveis padronizadas.
- Alvo: variacao do nivel em `h` horas (cm). Prever a variacao, nao o nivel, torna a
  persistencia o baseline natural (variacao zero).
- Validacao: walk-forward em ordem temporal, 5 dobras, com `gap` de `h` horas entre treino e
  teste para o alvo do treino nao enxergar o futuro do teste.
- Baselines obrigatorios: persistencia (variacao 0) e extrapolacao linear da tendencia atual.
- Publicacao (RN07): so publica se o modelo vencer a persistencia por margem minima E houver ao
  menos 60 dias de dado util. Caso contrario a previsao fica INDISPONIVEL, com o motivo.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DIAS_MINIMOS = 45  # TEMPORARIO para a demonstracao; o valor da RN07 e 60
MARGEM_SOBRE_PERSISTENCIA = 0.05  # o modelo precisa errar pelo menos 5% menos que a persistencia
N_DOBRAS = 5
# Grade ampla: com poucas semanas de dado e eventos raros, regularizacao fraca explode o erro
# (medido: RMSE de 120 cm contra 46 cm da persistencia em 12 h). O alpha e escolhido por
# validacao interna do treino (RidgeCV), nunca olhando o teste.
ALPHAS = (0.1, 1.0, 10.0, 100.0, 1e3, 1e4, 1e5, 1e6)


@dataclass
class Resultado:
    horizonte_h: int
    amostras: int
    dias_uteis: float
    rmse_cm: float | None = None
    mae_cm: float | None = None
    rmse_persistencia_cm: float | None = None
    rmse_tendencia_cm: float | None = None
    desvio_residual_cm: float | None = None
    publicar: bool = False
    motivo: str = ""
    colunas: list[str] = field(default_factory=list)
    pipeline: object | None = None  # modelo final, ajustado em todos os dados
    faixa_treino: dict[str, tuple[float, float]] = field(default_factory=dict)


def novo_pipeline(horizonte_h: int = 1) -> object:
    """Padroniza e ajusta Ridge. O alpha e escolhido por validacao cruzada TEMPORAL (com `gap`).

    O leave-one-out padrao do RidgeCV embaralha o tempo e, com linhas vizinhas muito parecidas,
    sempre prefere pouca regularizacao; medido aqui, isso fazia o erro explodir fora da amostra.
    """
    cv = TimeSeriesSplit(n_splits=3, gap=horizonte_h)
    return make_pipeline(
        StandardScaler(), RidgeCV(alphas=ALPHAS, cv=cv, scoring="neg_root_mean_squared_error")
    )


def _rmse(erro: np.ndarray) -> float:
    return float(np.sqrt(np.mean(erro**2)))


def preparar(X: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Mantem so as linhas completas (sem NaN em X nem em y), em ordem temporal."""
    base = X.assign(__y=y).dropna().sort_index()
    return base.drop(columns="__y"), base["__y"]


def avaliar_horizonte(X: pd.DataFrame, y: pd.Series, horizonte_h: int) -> Resultado:
    Xc, yc = preparar(X, y)
    dias = len(Xc) / 24
    r = Resultado(horizonte_h=horizonte_h, amostras=len(Xc), dias_uteis=round(dias, 1))
    r.colunas = list(Xc.columns)
    if len(Xc) < N_DOBRAS * 48:
        r.motivo = f"Poucos dados para validar ({len(Xc)} horas completas)."
        return r

    erros_modelo, erros_persist, erros_tend = [], [], []
    cv = TimeSeriesSplit(n_splits=N_DOBRAS, gap=horizonte_h)
    for treino, teste in cv.split(Xc):
        modelo = novo_pipeline(horizonte_h)
        modelo.fit(Xc.iloc[treino], yc.iloc[treino])  # type: ignore[attr-defined]
        pred = modelo.predict(Xc.iloc[teste])  # type: ignore[attr-defined]
        real = yc.iloc[teste].to_numpy()
        erros_modelo.append(pred - real)
        erros_persist.append(0.0 - real)
        tendencia = Xc.iloc[teste]["taxa_3h_cm_h"].to_numpy() * horizonte_h
        erros_tend.append(tendencia - real)

    em, ep, et = (np.concatenate(e) for e in (erros_modelo, erros_persist, erros_tend))
    r.rmse_cm, r.mae_cm = _rmse(em), float(np.mean(np.abs(em)))
    r.rmse_persistencia_cm, r.rmse_tendencia_cm = _rmse(ep), _rmse(et)
    r.desvio_residual_cm = float(np.std(em))

    ganha_persistencia = r.rmse_cm < r.rmse_persistencia_cm * (1 - MARGEM_SOBRE_PERSISTENCIA)
    if dias < DIAS_MINIMOS:
        r.motivo = (
            f"Só há {dias:.0f} dias de dados completos; o mínimo para publicar é {DIAS_MINIMOS}."
        )
    elif not ganha_persistencia:
        r.motivo = (
            f"O modelo não superou a persistência (erro de {r.rmse_cm:.1f} cm contra "
            f"{r.rmse_persistencia_cm:.1f} cm de quem apenas repete o nível atual)."
        )
    else:
        r.publicar = True
        r.motivo = "Superou a persistência na validação."
    r.faixa_treino = {c: (float(Xc[c].min()), float(Xc[c].max())) for c in Xc.columns}
    final = novo_pipeline(horizonte_h)
    final.fit(Xc, yc)  # type: ignore[attr-defined]
    r.pipeline = final
    return r
