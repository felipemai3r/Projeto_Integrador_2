"""Previsao de nivel e simulacao de cenario (CDU02, CDU03, CDU09).

RN07: so ha previsao se existe modelo PUBLICADO para o horizonte (superou a persistencia e ha
dado suficiente). Sem ele, a resposta diz que esta indisponivel e por que, e o painel observado
continua. Nada aqui inventa numero.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
from common.enums import Faixa
from common.models import Estacao, Modelo
from modelo.dados import chuva_horaria, nivel_horario
from modelo.features import (
    HORIZONTES_H,
    PONTOS_CHUVA,
    montar_features,
    pontos_chuva,
    vizinhos_nivel,
)
from modelo.inferencia import (
    JANELA_IMPUTACAO_H,
    aplicar_cenario,
    extrapola,
    imputar_chuva,
    intervalo_cm,
    obrigatorias_do_artefato,
    prever_variacao_cm,
)
from modelo.registry import carregar_artefato, publicados, ultimos_treinos
from modelo.treino import cm_br
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import consultas, risco
from api.schemas import ChuvaEstimada, PontoCenario, PrevisaoHorizonte, PrevisaoOut, ResumoModelo

HISTORICO_H = 24 * 8  # cobre a janela de 168 h das variaveis
IDADE_MAXIMA_H = 3  # a linha usada por um modelo nao pode ser mais velha que isso


@dataclass(frozen=True)
class Quadros:
    """Variaveis horarias candidatas a "linha atual": com a chuva medida e, se houve falha de
    leitura, com a chuva estimada pelos vizinhos (`imputar_chuva`, so na inferencia)."""

    medido: pd.DataFrame
    estimado: pd.DataFrame | None
    horas_estimadas: dict[str, pd.DatetimeIndex]


# linha escolhida para um modelo: (variaveis, hora, horas estimadas por ponto que ele usa)
Linha = tuple[pd.Series, pd.Timestamp, dict[str, int]]


# uma hora rotulada t so esta completa em t + 1h + 1 min (folga da leitura h001 que a fecha)
FECHAMENTO_DA_HORA = pd.Timedelta(hours=1, minutes=1)


def so_horas_fechadas(X: pd.DataFrame, agora: datetime) -> pd.DataFrame:
    """Tira as horas que ainda nao terminaram em `agora`.

    A linha `t` e o estado ao fim de [t, t+1h), e a chuva dela vem da leitura que fecha a hora
    (ate 1 min depois). A hora corrente tem nivel parcial e chuva em branco (ou incompleta): o
    modelo que aceita NaN a "aceitaria" e preveria sem saber a chuva, com o regime caindo em
    chuva forte e o intervalo explodindo. No treino toda linha e hora completa.
    """
    return X.loc[X.index <= pd.Timestamp(agora) - FECHAMENTO_DA_HORA]


def montar_quadros(s: Session, estacao: str, agora: datetime) -> Quadros | None:
    """Monta as variaveis das ultimas horas do alvo, ou None se nao ha nivel do proprio alvo.

    So entram os pontos de chuva do alvo (`ConfigAlvo.pontos_chuva`): o mesmo conjunto do treino,
    tambem na imputacao por vizinhos. Nao decide qual hora serve: isso depende das colunas de
    cada modelo (`escolher_linha`).
    """
    fim = agora.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    ini = fim - timedelta(hours=HISTORICO_H)
    chuva = {c: chuva_horaria(s, c, ini, fim) for c in pontos_chuva(estacao)}
    nivel = {c: nivel_horario(s, c, ini, fim) for c in (estacao, *vizinhos_nivel(estacao))}
    chuva = {c: v for c, v in chuva.items() if not v.empty}
    nivel = {c: v for c, v in nivel.items() if not v.empty}
    if estacao not in nivel:
        return None
    estimada, preenchidas = imputar_chuva(chuva)
    return Quadros(
        medido=so_horas_fechadas(montar_features(chuva, nivel, alvo=estacao), agora),
        estimado=(
            so_horas_fechadas(montar_features(estimada, nivel, alvo=estacao), agora)
            if preenchidas
            else None
        ),
        horas_estimadas=preenchidas,
    )


def _horas_completas(
    X: pd.DataFrame | None, colunas: list[str], limite: pd.Timestamp
) -> pd.DatetimeIndex:
    """Horas recentes (>= limite) em que TODAS as colunas pedidas tem valor."""
    if X is None or X.empty or any(c not in X.columns for c in colunas):
        return pd.DatetimeIndex([], tz="UTC")
    ok = X[colunas].notna().all(axis=1) & (X.index >= limite)
    return X.index[ok.to_numpy()]


def escolher_linha(
    quadros: Quadros,
    colunas: list[str],
    agora: datetime,
    obrigatorias: list[str] | None = None,
) -> Linha | None:
    """Linha MAIS RECENTE (ate IDADE_MAXIMA_H atras) com as colunas exigidas do modelo preenchidas.

    Modelo antigo (`obrigatorias` None): todas as `colunas` mais o nivel. Modelo que aceita NaN:
    so `obrigatorias` mais o nivel; as demais podem estar vazias (NaN, nunca zero) e o modelo
    lida com isso. So as colunas do proprio modelo contam: uma serra fora do ar nao afeta quem
    nao a usa, e cada horizonte (cada artefato) pode ficar com uma hora diferente. Para a mesma
    hora vale a chuva medida; so se ela nao completa as colunas se usa a estimada pelos vizinhos
    (no modelo que aceita NaN, quando a estimada deixa menos colunas vazias). Devolve None se
    nenhuma hora serve ("Sem dados recentes"). O terceiro item diz, por ponto de chuva que o
    modelo usa, quantas horas estimadas entraram nas janelas da linha (vazio se tudo foi medido).
    """
    exigidas = list(
        dict.fromkeys([*(colunas if obrigatorias is None else obrigatorias), "nivel_m"])
    )
    limite = pd.Timestamp(agora) - pd.Timedelta(hours=IDADE_MAXIMA_H)
    medidas = _horas_completas(quadros.medido, exigidas, limite)
    estimadas = _horas_completas(quadros.estimado, exigidas, limite)
    candidatas = medidas.union(estimadas)
    if candidatas.empty:
        return None
    t = candidatas.max()
    usar_estimada = t not in medidas
    if not usar_estimada and obrigatorias is not None and t in estimadas:
        # aceita NaN: a medida serve, mas a estimada pode deixar menos chuva em branco
        vazias_medida = quadros.medido.loc[t].reindex(colunas).isna().sum()
        vazias_estimada = quadros.estimado.loc[t].reindex(colunas).isna().sum()  # type: ignore[union-attr]
        usar_estimada = vazias_estimada < vazias_medida
    if not usar_estimada or quadros.estimado is None:
        return quadros.medido.loc[t], t, {}
    janela = pd.Timedelta(hours=JANELA_IMPUTACAO_H - 1)
    usadas = {}
    for cod, horas in quadros.horas_estimadas.items():
        prefixo = f"chuva_{PONTOS_CHUVA[cod]}_"
        if any(c.startswith(prefixo) for c in colunas):
            n = int(((horas >= t - janela) & (horas <= t)).sum())
            if n > 0:
                usadas[cod] = n
    return quadros.estimado.loc[t], t, usadas


def _base_observada(quadros: Quadros, agora: datetime) -> tuple[pd.Timestamp, float] | None:
    """Ultimo nivel recente do alvo, para mostrar o nivel-base mesmo sem horizonte disponivel."""
    limite = pd.Timestamp(agora) - pd.Timedelta(hours=IDADE_MAXIMA_H)
    nivel = quadros.medido["nivel_m"].dropna()
    nivel = nivel[nivel.index >= limite]
    return (nivel.index[-1], float(nivel.iloc[-1])) if not nivel.empty else None


def _chuva_estimada(s: Session, horas_por_ponto: dict[str, int]) -> list[ChuvaEstimada]:
    if not horas_por_ponto:
        return []
    nomes = dict(
        s.execute(
            select(Estacao.codigo, Estacao.nome).where(Estacao.codigo.in_(horas_por_ponto))
        ).all()
    )
    return [
        ChuvaEstimada(codigo=c, nome=nomes.get(c, c), horas=n)
        for c, n in sorted(horas_por_ponto.items())
    ]


def _pontos_cenario(s: Session, alvo: str) -> list[PontoCenario]:
    """Pontos de chuva que o modelo do alvo usa. Chuva em outro ponto nao muda a previsao."""
    codigos = list(pontos_chuva(alvo))
    nomes = dict(
        s.execute(select(Estacao.codigo, Estacao.nome).where(Estacao.codigo.in_(codigos))).all()
    )
    return [PontoCenario(codigo=c, nome=nomes.get(c, c)) for c in codigos]


def _resumo(m: Modelo) -> ResumoModelo:
    return ResumoModelo(
        id=m.id,
        treinado_em=m.treinado_em,
        amostras=m.amostras,
        rmse_cm=m.rmse_cm,
        rmse_persistencia_cm=m.rmse_persistencia_cm,
    )


def _motivo_indisponivel(treino: Modelo | None) -> str:
    if treino is None:
        return (
            "O modelo ainda não foi treinado. Precisamos de mais dados para estimar com segurança."
        )
    motivo = (treino.metadados or {}).get("motivo", "")
    # treinos antigos gravaram "45.2 cm": exibe sempre no formato brasileiro, com duas casas.
    # Treinos novos ja gravam "45,20 cm" (cm_br): o lookbehind impede casar so o "20 cm" e
    # reformatar um numero que ja esta no formato certo.
    motivo = re.sub(
        r"(?<![\d.,])(\d+(?:\.\d+)?) cm", lambda m: f"{cm_br(float(m.group(1)))} cm", motivo
    )
    return f"A previsão ainda não está disponível. {motivo}".strip()


def prever(
    s: Session,
    est: Estacao,
    agora: datetime,
    chuva_mm: dict[str, float] | None = None,
    janela_h: int = 6,
) -> PrevisaoOut:
    origem = "cenario" if chuva_mm is not None else "operacional"
    pub = publicados(s, est.id)
    treinos = ultimos_treinos(s, est.id)
    limiares = consultas.limiares_vigentes(s, est.id)
    quadros = montar_quadros(s, est.codigo, agora)

    horizontes: list[PrevisaoHorizonte] = []
    usadas: list[Linha] = []  # uma linha por horizonte disponivel (cada modelo escolhe a sua)
    for h in HORIZONTES_H:
        modelo = pub.get(h)
        if modelo is None:
            horizontes.append(
                PrevisaoHorizonte(
                    horizonte_h=h, disponivel=False, motivo=_motivo_indisponivel(treinos.get(h))
                )
            )
            continue
        escolhida = None
        artefato: dict = {}
        if quadros is not None:
            artefato = carregar_artefato(modelo.caminho_artefato)
            escolhida = escolher_linha(
                quadros, artefato["colunas"], agora, obrigatorias_do_artefato(artefato)
            )
        if escolhida is None:
            # sem nivel do alvo, ou nenhuma hora recente com as colunas DESTE modelo preenchidas
            horizontes.append(
                PrevisaoHorizonte(
                    horizonte_h=h,
                    disponivel=False,
                    modelo=_resumo(modelo),
                    motivo="Sem dados recentes o bastante para estimar agora. Só o observado.",
                )
            )
            continue
        linha, t, _ = escolhida
        usadas.append(escolhida)
        entrada = (
            aplicar_cenario(linha, chuva_mm, janela_h, alvo=est.codigo)
            if chuva_mm is not None
            else linha
        )
        delta_cm = prever_variacao_cm(artefato, entrada)
        nivel = float(linha["nivel_m"]) + delta_cm / 100
        # modelo novo: intervalo assimetrico do regime de chuva da linha usada (ADR 0006);
        # modelo antigo (sem `intervalo_por_regime`): +-1,96 desvios, como sempre
        limites = intervalo_cm(artefato, entrada, modelo.metadados)
        confianca = 0.95  # modelo antigo: +-1,96 sigma
        if limites is not None:
            inferior, superior = nivel + limites[0] / 100, nivel + limites[1] / 100
            incerteza = (limites[1] - limites[0]) / 2 / 100
            confianca = float(
                artefato.get("confianca_intervalo")
                or (modelo.metadados or {}).get("confianca_intervalo")
                or 0.95
            )
        else:
            sigma = ((modelo.metadados or {}).get("desvio_residual_cm") or modelo.rmse_cm) / 100
            inferior, superior, incerteza = nivel - 1.96 * sigma, nivel + 1.96 * sigma, 1.96 * sigma
        faixa = risco.classificar(nivel, limiares) if limiares else None
        horizontes.append(
            PrevisaoHorizonte(
                horizonte_h=h,
                disponivel=True,
                valido_para=(t + pd.Timedelta(hours=h)).to_pydatetime(),
                nivel_m=round(nivel, 2),
                incerteza_m=round(incerteza, 2),
                intervalo_m=(round(inferior, 2), round(superior, 2)),
                confianca=confianca,
                faixa=faixa.value if isinstance(faixa, Faixa) else None,
                modelo=_resumo(modelo),
                extrapolacao=extrapola(artefato, entrada),
            )
        )
    # base: a hora mais recente entre as linhas realmente usadas; sem nenhuma, o ultimo nivel
    # observado (horizonte indisponivel nao esconde o nivel de agora)
    base_t: pd.Timestamp | None = None
    base_nivel: float | None = None
    if usadas:
        linha, base_t, _ = max(usadas, key=lambda u: u[1])
        base_nivel = float(linha["nivel_m"])
    elif quadros is not None and (obs := _base_observada(quadros, agora)) is not None:
        base_t, base_nivel = obs
    # so avisa as estimativas de chuva que de fato entraram numa previsao (por ponto, o maximo
    # de horas estimadas entre as linhas usadas)
    estimada: dict[str, int] = {}
    for _, _, horas in usadas:
        for cod, n in horas.items():
            estimada[cod] = max(estimada.get(cod, 0), n)
    return PrevisaoOut(
        estacao=est.codigo,
        origem=origem,
        base_em=base_t.to_pydatetime() if base_t is not None else None,
        nivel_base_m=round(base_nivel, 2) if base_nivel is not None else None,
        horizontes=horizontes,
        chuva_estimada=_chuva_estimada(s, estimada),
        pontos_cenario=_pontos_cenario(s, est.codigo),
    )
