"""Valores fixos do dominio. Espelhados no front (web/src/lib)."""

from enum import StrEnum


class Papel(StrEnum):
    ALVO = "alvo"
    INFLUENCIA = "influencia"
    REFERENCIA = "referencia"


class Variavel(StrEnum):
    NIVEL_M = "nivel_m"
    # Serie de 5 em 5 minutos da API REST. A semantica exata do acumulado ainda precisa
    # ser confirmada com a fonte (fontes-de-dados.md, secao 4.2); guardamos como a fonte entrega.
    CHUVA_ACUMULADA_MM = "chuva_acumulada_mm"
    # Acumulados por janela entregues pelo GraphQL (instantaneo, uma leitura a cada coleta)
    CHUVA_H001_MM = "chuva_h001_mm"
    CHUVA_H003_MM = "chuva_h003_mm"
    CHUVA_H006_MM = "chuva_h006_mm"
    CHUVA_H012_MM = "chuva_h012_mm"
    CHUVA_H024_MM = "chuva_h024_mm"
    CHUVA_H048_MM = "chuva_h048_mm"
    CHUVA_H072_MM = "chuva_h072_mm"
    CHUVA_H168_MM = "chuva_h168_mm"
    RESERVATORIO_M = "reservatorio_m"
    RESERVATORIO_PCT = "reservatorio_pct"


class Qualidade(StrEnum):
    OK = "ok"
    SUSPEITA = "suspeita"
    DESCARTADA = "descartada"


class StatusColeta(StrEnum):
    SUCESSO = "sucesso"
    VAZIO = "vazio"
    FALHA = "falha"


class Faixa(StrEnum):
    NORMAL = "normal"
    OBSERVACAO = "observacao"
    ATENCAO = "atencao"
    ALERTA = "alerta"
