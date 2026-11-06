"""API com as estacoes do painel municipal: serras so de chuva e Revolver como segundo alvo."""

from datetime import timedelta

import pytest
from common.models import Estacao, Fonte, Leitura
from common.seed import semear
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tempo_api import AGORA


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def grava(
    s: Session,
    codigo: str,
    variavel: str,
    pontos: list[tuple[int, float]],
    fonte: str = "pdc_municipal",
    qualidade: str = "ok",
) -> None:
    """`pontos`: (minutos antes de AGORA, valor)."""
    est = s.scalars(select(Estacao.id).where(Estacao.codigo == codigo)).one()
    f = s.scalars(select(Fonte.id).where(Fonte.codigo == fonte)).one()
    for minutos, v in pontos:
        s.add(
            Leitura(
                estacao_id=est,
                variavel=variavel,
                valor=v,
                unidade="x",
                medido_em=AGORA - timedelta(minutes=minutos),
                fonte_id=f,
                qualidade=qualidade,
            )
        )
    s.commit()


def test_lista_de_estacoes_traz_as_tres_serras_sem_limiar_e_o_revolver_com_os_dele(
    client: TestClient, base: Session
) -> None:
    corpo = {e["codigo"]: e for e in client.get("/api/estacoes").json()}
    assert len(corpo) == 11
    for cod in ("DC-PEU-002", "DC-PEU-003", "DC-PEU-004"):
        assert corpo[cod]["papel"] == "influencia" and corpo[cod]["curso_dagua"] is None
        assert set(corpo[cod]["limiares"].values()) == {None}
    assert corpo["DCSC-00174"]["limiares"] == {
        "atencao": 2.5,
        "alerta": 3.0,
        "alerta_alto": 3.5,
        "extremo": None,
    }
    assert corpo["DCSC-00174"]["papel"] == "alvo"


def test_serra_nao_tem_nivel_e_diz_isso_sem_inventar_numero(
    client: TestClient, base: Session
) -> None:
    grava(base, "DC-PEU-002", "chuva_h001_mm", [(0, 0.4)])  # tem chuva, mas nao nivel
    r = client.get("/api/estacoes/DC-PEU-002/atual").json()
    assert r["estado"] == "indisponivel" and r["nivel_m"] is None
    assert r["faixa"] is None and r["tendencia"] is None and r["fonte"] is None
    assert "não tem leitura de nível" in r["motivo"]


def test_serra_com_nivel_hipotetico_vindo_da_fonte_nao_ganha_faixa_sem_limiar(
    client: TestClient, base: Session
) -> None:
    grava(base, "DC-PEU-003", "nivel_m", [(0, 9.0)])
    r = client.get("/api/estacoes/DC-PEU-003/atual").json()
    assert r["nivel_m"] == 9.0 and r["faixa"] is None


def test_nivel_do_revolver_vindo_do_painel_usa_os_limiares_do_revolver(
    client: TestClient, base: Session
) -> None:
    grava(base, "DCSC-00174", "nivel_m", [(10, 3.0), (5, 3.1), (0, 3.2)])
    r = client.get("/api/estacoes/DCSC-00174/atual").json()
    assert (r["nivel_m"], r["faixa"], r["fonte"]) == (3.2, "alerta", "pdc_municipal")
    assert r["estado"] == "ok"


def test_revolver_com_duas_fontes_mostra_a_leitura_mais_recente_de_qualquer_uma(
    client: TestClient, base: Session
) -> None:
    grava(base, "DCSC-00174", "nivel_m", [(8, 1.00)], fonte="pdc_municipal")
    grava(base, "DCSC-00174", "nivel_m", [(3, 1.10)], fonte="dcsc_graphql")
    r = client.get("/api/estacoes/DCSC-00174/atual").json()
    assert (r["nivel_m"], r["fonte"]) == (1.10, "dcsc_graphql")


def test_tendencia_do_revolver_mistura_as_duas_fontes_sem_dobrar_a_taxa(
    client: TestClient, base: Session
) -> None:
    # +0,10 m em 1 h, lido ora pelo painel ora pelo GraphQL com ~1 min de diferenca
    grava(
        base, "DCSC-00174", "nivel_m", [(120, 1.00), (60, 1.10), (0, 1.20)], fonte="pdc_municipal"
    )
    grava(base, "DCSC-00174", "nivel_m", [(119, 1.00), (59, 1.10), (1, 1.19)], fonte="dcsc_graphql")
    r = client.get("/api/estacoes/DCSC-00174/atual").json()
    assert r["taxa_cm_h"] == pytest.approx(10.0, abs=1.5)
    assert r["tendencia"] == "subindo"


def test_dado_do_revolver_velho_fica_desatualizado_e_mantem_a_faixa_do_ultimo_valor(
    client: TestClient, base: Session
) -> None:
    grava(base, "DCSC-00174", "nivel_m", [(90, 3.6)])
    r = client.get("/api/estacoes/DCSC-00174/atual").json()
    assert r["estado"] == "desatualizado" and r["faixa"] == "alerta_alto"
    assert r["motivo"].startswith("Dado desatualizado")


def test_leitura_suspeita_do_painel_nao_vira_o_nivel_atual(
    client: TestClient, base: Session
) -> None:
    grava(base, "DCSC-00174", "nivel_m", [(10, 1.0)])
    grava(base, "DCSC-00174", "nivel_m", [(0, 9.0)], qualidade="suspeita")
    assert client.get("/api/estacoes/DCSC-00174/atual").json()["nivel_m"] == 1.0


def test_serie_de_chuva_da_serra_agrega_a_chuva_de_uma_hora(
    client: TestClient, base: Session
) -> None:
    grava(base, "DC-PEU-004", "chuva_h001_mm", [(m, 2.0) for m in (30, 25, 20)])
    r = client.get(
        "/api/estacoes/DC-PEU-004/serie", params={"variavel": "chuva_h001_mm", "horas": 1}
    ).json()
    assert r["variavel"] == "chuva_h001_mm" and r["unidade"] == "x"
    assert [p["valor"] for p in r["pontos"]] == [2.0] * len(r["pontos"]) and r["pontos"]


def test_serie_de_nivel_da_serra_vem_vazia_e_sem_unidade(client: TestClient, base: Session) -> None:
    r = client.get("/api/estacoes/DC-PEU-004/serie", params={"horas": 24}).json()
    assert r["pontos"] == [] and r["unidade"] == ""


def _chuva(client: TestClient) -> dict[str, dict]:
    return {e["estacao"]: e for e in client.get("/api/chuva/acumulada").json()}


def test_chuva_acumulada_usa_a_leitura_medida_mais_recente_seja_qual_for_a_fonte(
    client: TestClient, base: Session
) -> None:
    grava(base, "DCSC-00037", "chuva_h001_mm", [(10, 1.3)], fonte="dcsc_graphql")
    grava(base, "DCSC-00037", "chuva_h001_mm", [(1, 9.9)], fonte="pdc_municipal")
    emma = _chuva(client)["DCSC-00037"]
    assert emma["acumulado_mm"]["1h"] == 9.9 and emma["fonte"] == "pdc_municipal"


def test_chuva_das_estacoes_novas_so_tem_a_janela_de_1h_e_o_resto_vem_nulo(
    client: TestClient, base: Session
) -> None:
    grava(base, "DC-PEU-002", "chuva_h001_mm", [(3, 4.2)])
    serra = _chuva(client)["DC-PEU-002"]
    assert serra["estado"] == "ok" and serra["fonte"] == "pdc_municipal"
    assert serra["acumulado_mm"]["1h"] == 4.2
    assert [v for j, v in serra["acumulado_mm"].items() if j != "1h"] == [None] * 7
    assert serra["medido_em"] is not None


def test_chuva_mistura_janelas_de_fontes_diferentes_na_mesma_estacao(
    client: TestClient, base: Session
) -> None:
    grava(base, "DCSC-00037", "chuva_h024_mm", [(4, 30.0)], fonte="dcsc_graphql")
    grava(base, "DCSC-00037", "chuva_h001_mm", [(2, 1.5)], fonte="pdc_municipal")
    acum = _chuva(client)["DCSC-00037"]["acumulado_mm"]
    assert acum["1h"] == 1.5 and acum["24h"] == 30.0


def test_chuva_da_reanalise_era5_nunca_entra_como_medicao(
    client: TestClient, base: Session
) -> None:
    grava(base, "DC-PEU-003", "chuva_h001_mm", [(5, 7.7)], fonte="openmeteo_archive")
    serra = _chuva(client)["DC-PEU-003"]
    assert serra["estado"] == "indisponivel" and serra["fonte"] is None
    assert serra["acumulado_mm"]["1h"] is None
    # e nao esconde a medicao quando as duas existem, mesmo sendo a do ERA5 mais nova
    grava(base, "DC-PEU-003", "chuva_h001_mm", [(20, 0.4)])
    serra = _chuva(client)["DC-PEU-003"]
    assert serra["acumulado_mm"]["1h"] == 0.4 and serra["fonte"] == "pdc_municipal"


def test_chuva_antiga_da_estacao_nova_aparece_como_desatualizada(
    client: TestClient, base: Session
) -> None:
    grava(base, "DC-PEU-004", "chuva_h001_mm", [(180, 1.0)])
    assert _chuva(client)["DC-PEU-004"]["estado"] == "desatualizado"


def test_chuva_leitura_suspeita_nao_aparece(client: TestClient, base: Session) -> None:
    grava(base, "DC-PEU-004", "chuva_h001_mm", [(2, 50.0)], qualidade="suspeita")
    assert _chuva(client)["DC-PEU-004"]["estado"] == "indisponivel"


def test_chuva_acumulada_lista_todas_as_estacoes_ativas_inclusive_as_de_serra(
    client: TestClient, base: Session
) -> None:
    codigos = {e["estacao"] for e in client.get("/api/chuva/acumulada").json()}
    assert {"DC-PEU-002", "DC-PEU-003", "DC-PEU-004", "DCSC-00174"} <= codigos
    assert len(codigos) == 11


def test_estacao_desativada_some_da_lista_e_da_chuva(client: TestClient, base: Session) -> None:
    base.scalars(select(Estacao).where(Estacao.codigo == "DC-PEU-003")).one().ativa = False
    base.commit()
    assert "DC-PEU-003" not in {e["codigo"] for e in client.get("/api/estacoes").json()}
    assert "DC-PEU-003" not in {e["estacao"] for e in client.get("/api/chuva/acumulada").json()}
    assert client.get("/api/estacoes/DC-PEU-003/atual").status_code == 404


def test_previsao_de_serra_nao_quebra_e_diz_que_nao_ha_modelo(
    client: TestClient, base: Session
) -> None:
    r = client.get("/api/previsao/DC-PEU-002")
    assert r.status_code == 200
    corpo = r.json()
    assert not any(h["disponivel"] for h in corpo["horizontes"])
    assert corpo["base_em"] is None and corpo["nivel_base_m"] is None


def test_simulacao_com_ponto_desconhecido_e_aceita_e_com_estacao_desconhecida_da_404(
    client: TestClient, base: Session
) -> None:
    ok = client.post(
        "/api/simulacao", json={"estacao": "DCSC-00174", "chuva_mm": {"XYZ": 10}, "janela_h": 6}
    )
    assert ok.status_code == 200 and ok.json()["origem"] == "cenario"
    nao = client.post("/api/simulacao", json={"estacao": "XYZ", "chuva_mm": {"A": 1}})
    assert nao.status_code == 404


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ({"estacao": "DCSC-00174", "chuva_mm": {}, "janela_h": 6}, "pelo menos um ponto"),
        ({"estacao": "DCSC-00174", "chuva_mm": {"DCSC-00043": -1}, "janela_h": 6}, "entre 0 e 400"),
        (
            {"estacao": "DCSC-00174", "chuva_mm": {"DC-PEU-003": 400.1}, "janela_h": 6},
            "entre 0 e 400",
        ),
        ({"estacao": "DCSC-00174", "chuva_mm": {"DCSC-00043": 5}, "janela_h": 25}, "1 e 24"),
        ({"estacao": "DCSC-00174", "chuva_mm": {"DCSC-00043": 5}, "janela_h": 0}, "1 e 24"),
    ],
)
def test_simulacao_valida_os_limites_da_entrada(
    client: TestClient, base: Session, corpo: dict, trecho: str
) -> None:
    r = client.post("/api/simulacao", json=corpo)
    assert r.status_code == 422 and trecho in str(r.json()["detail"])


@pytest.mark.parametrize("mm", [0, 400])
def test_simulacao_aceita_os_valores_extremos_permitidos(
    client: TestClient, base: Session, mm: float
) -> None:
    r = client.post(
        "/api/simulacao",
        json={"estacao": "DCSC-00043", "chuva_mm": {"DCSC-00043": mm}, "janela_h": 24},
    )
    assert r.status_code == 200
