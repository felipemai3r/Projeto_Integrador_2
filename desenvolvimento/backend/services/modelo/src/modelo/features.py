"""Montagem das variaveis do modelo (docs/especificacao-completa.md, secao 9.2).

REGRA DE OURO, sem excecao: toda variavel na hora `t` usa so dado ate `t`. Janelas de chuva
terminam em `t`; diferencas olham para tras; o alvo (futuro) e construido a parte e nunca entra
em X. Ha teste que prova isso cortando a serie em `t` e comparando.

Convencao do rotulo: a hora de rotulo `t` cobre [t, t+1h) e a linha `t` representa o estado ao
FIM dessa hora (nivel medio e chuva de [t, t+1h), `valido_para = t + h`). A chuva de `t` e tudo
que se sabe ate t+1h; o que acontece depois so entra no alvo. A chuva por h001 (dados.py) usa a
leitura que fecha a hora, com folga de no maximo 1 min depois dela.

Cada hora sem cobertura vira NaN (nunca zero). O modelo aceita NaN (ADR 0006): so as colunas
obrigatorias (`treino.COLUNAS_OBRIGATORIAS`) tiram a linha do treino.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

HORIZONTES_H = (1, 3, 6, 12, 24)
JANELAS_CHUVA_H = (1, 3, 6, 12, 24, 48, 72, 168)
ALVO = "DCSC-00043"  # alvo padrao (e o unico que existia antes do Revolver)
# ponto de chuva -> rotulo curto usado nos nomes das variaveis. O rotulo e FIXO por estacao
# (nao depende do alvo): o modelo salvo em artefato guarda os nomes das colunas, e a simulacao
# (inferencia.aplicar_cenario) traduz codigo -> rotulo por este mesmo dicionario. Este e so o
# registro de rotulos: QUAIS pontos entram em cada alvo e `ConfigAlvo.pontos_chuva`.
PONTOS_CHUVA = {
    "DCSC-00043": "local",
    "DCSC-00037": "emma",
    "DCSC-00021": "boiteux",
    "DCSC-00015": "witmarsum",
    "DCSC-00036": "vitor",
    # fontes novas (painel municipal): chuva do proprio Revolver e tres estacoes de serra
    "DCSC-00174": "revolver",
    "DC-PEU-003": "serra_indios",  # Serra dos Indios, cabeceira do rio dos Indios
    "DC-PEU-004": "serra_vencida",  # Serra Vencida
    "DC-PEU-002": "serra_mirador",  # Serra Mirador / Mirante das Antenas
}
# Conjunto de chuva e vizinhos de nivel de uma estacao FORA de ALVOS (era o padrao do rio dos
# Indios, que hoje tem o proprio ConfigAlvo: ADR 0006). O conjunto de cada alvo e FIXO: o
# retreino diario nao pode acrescentar variaveis ao modelo publicado sem uma decisao (ADR 0005).
PONTOS_CHUVA_PADRAO = (
    "DCSC-00043",
    "DCSC-00037",
    "DCSC-00021",
    "DCSC-00015",
    "DCSC-00036",
)
NIVEL_VIZINHOS = {"DCSC-00021": "boiteux", "DCSC-00020": "ibirama"}


@dataclass(frozen=True)
class ConfigAlvo:
    """O que muda de uma estacao-alvo para outra."""

    codigo: str
    nome: str
    nivel_vizinhos: dict[str, str]  # estacao de nivel -> rotulo curto
    # estacoes cuja chuva vira variavel deste alvo (ordem = ordem das colunas). O rotulo vem de
    # PONTOS_CHUVA. Treino, inferencia, imputacao por vizinhos e simulacao usam so este conjunto.
    pontos_chuva: tuple[str, ...] = PONTOS_CHUVA_PADRAO
    # interacoes da hipotese do coordenador / remanso do Ibirama (so valem com Boiteux e Ibirama,
    # ou seja, para estacao fora de ALVOS)
    interacoes: bool = True
    # janela de treino padrao em dias; None = todo o historico (desde treinar.INICIO_HISTORICO).
    # Depende de onde vem cada variavel do alvo: ver ADR 0005 e 0006.
    janela_dias: int | None = None


ALVOS: dict[str, ConfigAlvo] = {
    # Rio dos Indios: todo o historico (desde 13/09/2025) e chuva do painel municipal, serras e
    # Revolver. Boiteux e Ibirama SAIRAM por ora: so tem ~4 meses de serie (API REST) e, com NaN
    # no resto do periodo, pioraram a validacao em 12 h (0,93) e 24 h (1,00 da persistencia).
    # Voltar a testar quando tiverem >= 1 ano (ADR 0006). Sem interacoes explicitas: o gradient
    # boosting as aprende sozinho.
    "DCSC-00043": ConfigAlvo(
        "DCSC-00043",
        "Rio dos Índios (Presidente Getúlio)",
        {},
        pontos_chuva=(
            "DCSC-00043",
            "DCSC-00037",
            "DCSC-00015",
            "DCSC-00174",
            "DC-PEU-003",
            "DC-PEU-004",
            "DC-PEU-002",
        ),
        interacoes=False,
        janela_dias=None,
    ),
    # Ribeirao Revolver: bacia urbana pequena que desagua no rio dos Indios dentro da cidade.
    # - O unico vizinho de nivel e o proprio rio dos Indios em Presidente Getulio (DCSC-00043):
    #   com ele cheio, o Revolver escoa pior (remanso); e o nivel mais proximo e mais relevante.
    # - Boiteux e Ibirama ficam de fora: sao pontos do Itajai do Norte/Itajai-Acu, com
    #   propagacao de horas a dias, escala errada para uma bacia que responde em 1 a 6 h. O
    #   efeito deles ja chega ao Revolver atraves do rio dos Indios.
    # - Sem interacoes: a de Dona Emma x Boiteux e do rio grande, e a de Ibirama x chuva local
    #   depende de um vizinho que o Revolver nao tem.
    # - Chuva: o pluviometro do proprio Revolver, a chuva "local" (DCSC-00043, na cidade) e as
    #   tres serras da cabeceira. Dona Emma e Witmarsum ficam de fora: estao no Itajai do Norte,
    #   em outra bacia e a dezenas de km, e a bacia do Revolver responde em 1 a 6 h; seguem a
    #   mesma logica que tirou Boiteux e Ibirama (escala errada) e custariam 16 colunas e linhas
    #   completas por coisa que a chuva local e das serras ja cobre. Vitor (DCSC-00036) tambem.
    "DCSC-00174": ConfigAlvo(
        "DCSC-00174",
        "Ribeirão Revólver",
        {"DCSC-00043": "getulio"},
        pontos_chuva=(
            "DCSC-00043",
            "DCSC-00174",
            "DC-PEU-003",
            "DC-PEU-004",
            "DC-PEU-002",
        ),
        interacoes=False,
        janela_dias=None,  # todas as variaveis vem do painel municipal, com 14 meses
    ),
}


def config_alvo(codigo: str) -> ConfigAlvo:
    """Configuracao do alvo. Estacao desconhecida usa os vizinhos do alvo padrao."""
    if codigo in ALVOS:
        return ALVOS[codigo]
    return ConfigAlvo(codigo, codigo, NIVEL_VIZINHOS, PONTOS_CHUVA_PADRAO)


def pontos_chuva(codigo: str) -> dict[str, str]:
    """Pontos de chuva do alvo: codigo da estacao -> rotulo curto (rotulo fixo por estacao)."""
    return {c: PONTOS_CHUVA[c] for c in config_alvo(codigo).pontos_chuva}


def vizinhos_nivel(codigo: str) -> dict[str, str]:
    """Estacoes de nivel vizinhas do alvo. Nunca inclui o proprio alvo."""
    return {c: r for c, r in config_alvo(codigo).nivel_vizinhos.items() if c != codigo}


MIN_COBERTURA_LONGA = 0.9  # janelas de 12 h ou mais toleram 10% de falha (reescaladas)
JANELA_MIN_TOLERANTE_H = 12  # abaixo disso a janela exige todas as horas


def chuva_acumulada(chuva_h: pd.Series, janela: int) -> pd.Series:
    """Soma da chuva nas ultimas `janela` horas ate t. Janelas longas toleram pouca falha.

    Uma unica hora sem cobertura (estacao com poucas leituras) nao pode zerar a previsao por
    12 ou 24 h, por isso essas janelas tambem toleram falha pequena.
    """
    if janela < JANELA_MIN_TOLERANTE_H:
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
    cfg = config_alvo(alvo)
    n_alvo = nivel[alvo]
    cols["nivel_m"] = n_alvo
    cols["taxa_1h_cm"] = n_alvo.diff(1) * 100
    cols["taxa_3h_cm_h"] = n_alvo.diff(3) * 100 / 3
    cols["aceleracao_cm"] = cols["taxa_1h_cm"].diff(1)
    # tendencia de prazo mais longo e faixa de variacao das ultimas 24 h (so o passado)
    cols["taxa_6h_cm_h"] = n_alvo.diff(6) * 100 / 6
    cols["taxa_24h_cm_h"] = n_alvo.diff(24) * 100 / 24
    cols["nivel_min_24h_m"] = n_alvo.rolling(24, min_periods=18).min()
    cols["nivel_max_24h_m"] = n_alvo.rolling(24, min_periods=18).max()

    for cod, rotulo in vizinhos_nivel(alvo).items():
        if cod in nivel:
            cols[f"nivel_{rotulo}_m"] = nivel[cod]
            cols[f"taxa_{rotulo}_1h_cm"] = nivel[cod].diff(1) * 100

    for cod, rotulo in pontos_chuva(alvo).items():
        if cod in chuva:
            for j in JANELAS_CHUVA_H:
                cols[f"chuva_{rotulo}_{j}h"] = chuva_acumulada(chuva[cod], j)

    # interacoes que testam a hipotese do coordenador e o remanso (secao 1.2)
    if cfg.interacoes and "chuva_emma_6h" in cols and "chuva_boiteux_6h" in cols:
        cols["emma_x_boiteux_6h"] = cols["chuva_emma_6h"] * cols["chuva_boiteux_6h"]
    if cfg.interacoes and "nivel_ibirama_m" in cols and "chuva_local_3h" in cols:
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
