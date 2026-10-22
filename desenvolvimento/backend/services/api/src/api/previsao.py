"""Previsao de nivel e simulacao de cenario (CDU02, CDU03, CDU09).

RN07: so ha previsao se existe modelo PUBLICADO para o horizonte (superou a persistencia e ha
dado suficiente). Sem ele, a resposta diz que esta indisponivel e por que, e o painel observado
continua. Nada aqui inventa numero.
"""

import re
from datetime import datetime, timedelta

import pandas as pd
from common.enums import Faixa
from common.models import Estacao, Modelo
from modelo.dados import chuva_horaria, nivel_horario
from modelo.features import HORIZONTES_H, NIVEL_VIZINHOS, PONTOS_CHUVA, montar_features
from modelo.inferencia import aplicar_cenario, extrapola, prever_variacao_cm
from modelo.registry import carregar_artefato, publicados, ultimos_treinos
from modelo.treino import cm_br
from sqlalchemy.orm import Session

from api import consultas, risco
from api.schemas import PrevisaoHorizonte, PrevisaoOut, ResumoModelo

HISTORICO_H = 24 * 8  # cobre a janela de 168 h das variaveis
IDADE_MAXIMA_H = 3  # a ultima linha completa nao pode ser mais velha que isso


def linha_atual(s: Session, estacao: str, agora: datetime) -> tuple[pd.Series, pd.Timestamp] | None:
    """Variaveis da ultima hora completa, ou None se os dados nao permitem (lacuna, falha)."""
    fim = agora.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    ini = fim - timedelta(hours=HISTORICO_H)
    chuva = {c: chuva_horaria(s, c, ini, fim) for c in PONTOS_CHUVA}
    nivel = {c: nivel_horario(s, c, ini, fim) for c in (estacao, *NIVEL_VIZINHOS)}
    chuva = {c: v for c, v in chuva.items() if not v.empty}
    nivel = {c: v for c, v in nivel.items() if not v.empty}
    if estacao not in nivel:
        return None
    X = montar_features(chuva, nivel, alvo=estacao).dropna()
    if X.empty:
        return None
    t = X.index[-1]
    if pd.Timestamp(agora) - t > pd.Timedelta(hours=IDADE_MAXIMA_H):
        return None
    return X.iloc[-1], t


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
    # treinos antigos gravaram "45.2 cm": exibe sempre no formato brasileiro, com duas casas
    motivo = re.sub(r"(\d+(?:\.\d+)?) cm", lambda m: f"{cm_br(float(m.group(1)))} cm", motivo)
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
    base = linha_atual(s, est.codigo, agora)

    horizontes: list[PrevisaoHorizonte] = []
    for h in HORIZONTES_H:
        modelo = pub.get(h)
        if modelo is None:
            horizontes.append(
                PrevisaoHorizonte(
                    horizonte_h=h, disponivel=False, motivo=_motivo_indisponivel(treinos.get(h))
                )
            )
            continue
        if base is None:
            horizontes.append(
                PrevisaoHorizonte(
                    horizonte_h=h,
                    disponivel=False,
                    modelo=_resumo(modelo),
                    motivo="Sem dados recentes o bastante para estimar agora. Só o observado.",
                )
            )
            continue
        linha, t = base
        entrada = aplicar_cenario(linha, chuva_mm, janela_h) if chuva_mm is not None else linha
        artefato = carregar_artefato(modelo.caminho_artefato)
        delta_cm = prever_variacao_cm(artefato, entrada)
        nivel = float(linha["nivel_m"]) + delta_cm / 100
        sigma = ((modelo.metadados or {}).get("desvio_residual_cm") or modelo.rmse_cm) / 100
        faixa = risco.classificar(nivel, limiares) if limiares else None
        horizontes.append(
            PrevisaoHorizonte(
                horizonte_h=h,
                disponivel=True,
                valido_para=(t + pd.Timedelta(hours=h)).to_pydatetime(),
                nivel_m=round(nivel, 2),
                incerteza_m=round(1.96 * sigma, 2),
                intervalo_m=(round(nivel - 1.96 * sigma, 2), round(nivel + 1.96 * sigma, 2)),
                faixa=faixa.value if isinstance(faixa, Faixa) else None,
                modelo=_resumo(modelo),
                extrapolacao=extrapola(artefato, entrada),
            )
        )
    return PrevisaoOut(
        estacao=est.codigo,
        origem=origem,
        base_em=base[1].to_pydatetime() if base else None,
        nivel_base_m=round(float(base[0]["nivel_m"]), 2) if base else None,
        horizontes=horizontes,
    )
