"""Carga inicial idempotente: fontes, estacoes e limiares oficiais do municipio.

Uso: python -m common.seed
Coordenadas vindas da propria API da Defesa Civil de SC (conferidas em 12/10/2026) e, para as
estacoes DC-PEU-*, da API do painel municipal (conferidas em 05/11/2026).
Pode rodar a cada subida do compose: so insere o que ainda nao existe.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db import sessao
from common.enums import Faixa, Papel
from common.models import Estacao, Fonte, Limiar

FONTES = [
    (
        "dcsc_graphql",
        "Defesa Civil SC, GraphQL Qualle",
        "https://monitoramento.defesacivil.sc.gov.br/graphql",
        300,
    ),
    ("dcsc_rest", "Defesa Civil SC, API REST", "https://api-dcsc.mks-unifique.ddns.net", 1800),
    (
        "dcsc_barragens",
        "Defesa Civil SC, barragens",
        "https://api-dcsc.mks-unifique.ddns.net/api/barragens",
        1800,
    ),
    ("openmeteo_forecast", "Open-Meteo, previsao", "https://api.open-meteo.com/v1/forecast", 3600),
    (
        "openmeteo_archive",
        "Open-Meteo, reanalise ERA5",
        "https://archive-api.open-meteo.com/v1/archive",
        2592000,
    ),
    ("ana_hidroweb", "ANA, HidroWebService", "https://www.snirh.gov.br/hidrowebservice", 86400),
    (
        "pdc_municipal",
        "Defesa Civil de Presidente Getúlio, API do painel",
        "https://uizatcahxcyscjbkxnzp.supabase.co/functions/v1/stations-api",
        300,
    ),
]

# codigo, nome, curso d'agua, latitude, longitude, papel, fonte
ESTACOES = [
    ("DCSC-00043", "PCD Presidente Getúlio", "Rio dos Índios", -27.045497, -49.624281, Papel.ALVO),
    ("DCSC-00174", "PCD ZAS Creche", "Ribeirão Revólver", -27.055103, -49.615509, Papel.ALVO),
    (
        "DCSC-00021",
        "PCD José Boiteux",
        "Rio Itajaí do Norte",
        -26.954842,
        -49.633591,
        Papel.INFLUENCIA,
    ),
    ("DCSC-00037", "PCD Dona Emma", None, -26.985990, -49.729790, Papel.INFLUENCIA),
    ("DCSC-00015", "PCD Witmarsum", None, -26.915739, -49.839573, Papel.INFLUENCIA),
    ("DCSC-00036", "PCD Vitor Meireles", None, -26.880632, -49.839600, Papel.INFLUENCIA),
    (
        "DCSC-00042",
        "Barragem Norte José Boiteux",
        "Itajaí do Norte",
        -26.892469,
        -49.682358,
        Papel.INFLUENCIA,
    ),
    ("DCSC-00020", "PCD Ibirama", "Rio Itajaí do Norte", -27.056997, -49.519951, Papel.REFERENCIA),
]

# Estacoes que so existem na API do painel municipal (PDC). Medem apenas chuva; a quarta estacao
# fisica do painel, a Creche (DC-PEU-001), e a mesma DCSC-00174 acima e nao ganha cadastro novo.
# Os codigos DC-PEU-* sao os da propria fonte e o modelo os usa como estao.
ESTACOES_PDC = [
    (
        "DC-PEU-002",
        "PCD Serra Mirador (Mirante das Antenas)",
        None,
        -27.08598518371582,
        -49.58824920654297,
        Papel.INFLUENCIA,
    ),
    (
        "DC-PEU-003",
        "PCD Serra dos Índios (Posto de Saúde)",
        None,
        -27.085325241088867,
        -49.815765380859375,
        Papel.INFLUENCIA,
    ),
    (
        "DC-PEU-004",
        "PCD Serra Vencida (Escola Serra Vencida)",
        None,
        -27.123065948486328,
        -49.723419189453125,
        Papel.INFLUENCIA,
    ),
]

# Limiares do painel municipal (RN01), pendentes de confirmacao formal (PE05)
LIMIARES = {
    "DCSC-00043": {Faixa.ATENCAO: 4.00, Faixa.ALERTA: 4.50, Faixa.ALERTA_ALTO: 5.50},
    "DCSC-00174": {Faixa.ATENCAO: 2.50, Faixa.ALERTA: 3.00, Faixa.ALERTA_ALTO: 3.50},
}
JUSTIFICATIVA = "Limiar do painel da Defesa Civil municipal, pendente de confirmacao formal (PE05)"


def semear(s: Session) -> None:
    fontes: dict[str, Fonte] = {}
    for codigo, nome, url, freq in FONTES:
        f = s.scalar(select(Fonte).where(Fonte.codigo == codigo))
        if f is None:
            f = Fonte(codigo=codigo, nome=nome, base_url=url, frequencia_s=freq)
            s.add(f)
        fontes[codigo] = f
    s.flush()

    estacoes: dict[str, Estacao] = {}
    # fonte_id da estacao = fonte pela qual ela e conhecida; a leitura guarda a sua propria fonte
    cadastro = [(*e, "dcsc_graphql") for e in ESTACOES]
    cadastro += [(*e, "pdc_municipal") for e in ESTACOES_PDC]
    for codigo, nome, curso, lat, lon, papel, fonte in cadastro:
        e = s.scalar(select(Estacao).where(Estacao.codigo == codigo))
        if e is None:
            e = Estacao(
                codigo=codigo,
                nome=nome,
                curso_dagua=curso,
                latitude=lat,
                longitude=lon,
                papel=papel.value,
                fonte_id=fontes[fonte].id,
            )
            s.add(e)
        estacoes[codigo] = e
    s.flush()

    for codigo, faixas in LIMIARES.items():
        for faixa, valor in faixas.items():
            existe = s.scalar(
                select(Limiar).where(
                    Limiar.estacao_id == estacoes[codigo].id, Limiar.faixa == faixa.value
                )
            )
            if existe is None:
                s.add(
                    Limiar(
                        estacao_id=estacoes[codigo].id,
                        faixa=faixa.value,
                        valor_m=valor,
                        autor="equipe",
                        justificativa=JUSTIFICATIVA,
                    )
                )


if __name__ == "__main__":
    with sessao() as s:
        semear(s)
    print("seed concluido")
