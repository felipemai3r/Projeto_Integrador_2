from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from common.models import Estacao, Modelo
from common.seed import semear
from fastapi.testclient import TestClient
from modelo.features import PONTOS_CHUVA, alvo_deslocado, montar_features
from modelo.inferencia import MAX_HORAS_IMPUTADAS
from modelo.treino import avaliar_horizonte
from sqlalchemy import select
from sqlalchemy.orm import Session
from tempo_api import AGORA

from api.previsao import Quadros, escolher_linha, montar_quadros


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-07-01", periods=n, freq="1h", tz="UTC")


def _treinar_artefato(
    horizonte: int = 3,
    alvo: str = "DCSC-00043",
    com_serras: bool = False,
    extras: tuple[str, ...] = (),
):
    rng = np.random.default_rng(1)
    n = 24 * 120
    chuva = pd.Series(np.where(rng.random(n) < 0.08, rng.gamma(2.0, 3.0, n), 0.0), _idx(n))
    resposta = np.zeros(n)
    resposta[2:] = chuva.to_numpy()[: n - 2] * 0.02
    nivel = pd.Series(1.0 + np.cumsum(resposta - 0.003), _idx(n)).clip(lower=0.5)
    chuvas = {"DCSC-00043": chuva, "DCSC-00037": chuva.shift(1).fillna(0)}
    if com_serras:
        chuvas |= {"DC-PEU-003": chuva * 1.5, "DC-PEU-004": chuva.shift(2).fillna(0)}
    for cod in extras:  # pontos de chuva a mais que o modelo passa a usar
        chuvas[cod] = chuva.shift(3).fillna(0)
    niveis = {
        "DCSC-00043": nivel,
        "DCSC-00021": nivel * 1.1,
        "DCSC-00020": nivel * 0.9,
        "DCSC-00174": nivel * 0.8,
    }
    X = montar_features(chuvas, niveis, alvo=alvo)
    r = avaliar_horizonte(X, alvo_deslocado(niveis[alvo], horizonte), horizonte)
    return r, X.dropna().iloc[-1]


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def _est(s: Session, codigo: str = "DCSC-00043") -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()


def _publicar(
    s: Session,
    tmp: Path,
    horizonte: int = 3,
    codigo: str = "DCSC-00043",
    com_serras: bool = False,
    extras: tuple[str, ...] = (),
) -> tuple[Modelo, pd.Series]:
    r, linha = _treinar_artefato(horizonte, codigo, com_serras, extras)
    assert r.pipeline is not None
    caminho = tmp / f"m{codigo}_{horizonte}.joblib"
    joblib.dump(
        {"pipeline": r.pipeline, "colunas": r.colunas, "faixa_treino": r.faixa_treino}, caminho
    )
    m = Modelo(
        estacao_id=_est(s, codigo).id,
        horizonte_h=horizonte,
        algoritmo="ridge",
        treinado_em=AGORA,
        amostras=r.amostras,
        rmse_cm=r.rmse_cm or 1.0,
        mae_cm=1.0,
        rmse_persistencia_cm=r.rmse_persistencia_cm or 2.0,
        publicado=True,
        caminho_artefato=str(caminho),
        metadados={"desvio_residual_cm": r.desvio_residual_cm or 1.0, "motivo": "ok"},
    )
    s.add(m)
    s.commit()
    return m, linha


def _com_linha(monkeypatch: pytest.MonkeyPatch, linha: pd.Series | None) -> None:
    """Fixa as variaveis "de agora": uma unica hora (1 h atras) com os valores de `linha`."""
    quadros = (
        Quadros(
            medido=pd.DataFrame(
                [linha.to_numpy()],
                index=[pd.Timestamp(AGORA - timedelta(hours=1))],
                columns=linha.index,
            ),
            estimado=None,
            horas_estimadas={},
        )
        if linha is not None
        else None
    )
    monkeypatch.setattr("api.previsao.montar_quadros", lambda s, estacao, agora: quadros)


def test_sem_modelo_publicado_nao_inventa_numero_e_explica(
    client: TestClient, base: Session
) -> None:
    base.add(
        Modelo(
            estacao_id=_est(base).id,
            horizonte_h=6,
            algoritmo="ridge",
            treinado_em=AGORA,
            amostras=1200,
            rmse_cm=40.0,
            mae_cm=20.0,
            rmse_persistencia_cm=30.0,
            publicado=False,
            caminho_artefato="",
            metadados={"motivo": "O modelo não superou a persistência."},
        )
    )
    base.commit()
    r = client.get("/api/previsao/DCSC-00043").json()
    assert [h["disponivel"] for h in r["horizontes"]] == [False] * 5
    assert all(h["nivel_m"] is None and h["intervalo_m"] is None for h in r["horizontes"])
    seis = next(h for h in r["horizontes"] if h["horizonte_h"] == 6)
    assert "não superou a persistência" in seis["motivo"]
    assert "ainda não foi treinado" in r["horizontes"][0]["motivo"]
    assert "fonte oficial" in r["aviso"].lower()


def test_horizonte_publicado_traz_valor_intervalo_e_faixa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, linha = _publicar(base, tmp_path, 3)
    _com_linha(monkeypatch, linha)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] and tres["faixa"] in (
        "normal",
        "atencao",
        "alerta",
        "alerta_alto",
        "extremo",
        None,
    )
    lo, hi = tres["intervalo_m"]
    assert lo < tres["nivel_m"] < hi and tres["incerteza_m"] > 0
    assert tres["modelo"]["rmse_cm"] > 0
    assert r["origem"] == "operacional" and r["nivel_base_m"] is not None
    # os demais seguem indisponiveis
    assert [h["disponivel"] for h in r["horizontes"] if h["horizonte_h"] != 3] == [False] * 4


def test_sem_dados_recentes_modelo_existe_mas_nao_estima(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)
    _com_linha(monkeypatch, None)
    tres = next(
        h
        for h in client.get("/api/previsao/DCSC-00043").json()["horizontes"]
        if h["horizonte_h"] == 3
    )
    assert tres["disponivel"] is False and "Sem dados recentes" in tres["motivo"]


def test_simulacao_com_mais_chuva_estima_nivel_maior_e_marca_cenario(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, linha = _publicar(base, tmp_path, 3)
    _com_linha(monkeypatch, linha)

    def nivel(mm: float) -> float:
        r = client.post(
            "/api/simulacao", json={"chuva_mm": {"DCSC-00043": mm, "DCSC-00037": mm}, "janela_h": 6}
        ).json()
        assert r["origem"] == "cenario"
        return next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["nivel_m"]

    assert nivel(30.0) > nivel(0.0)


def test_simulacao_muito_fora_do_treino_sinaliza_extrapolacao(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, linha = _publicar(base, tmp_path, 3)
    _com_linha(monkeypatch, linha)
    r = client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": 400}, "janela_h": 1}).json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert "chuva_local_1h" in tres["extrapolacao"]


def test_simulacao_valida_a_entrada(client: TestClient, base: Session) -> None:
    ok = {"DCSC-00043": 10}
    assert client.post("/api/simulacao", json={"chuva_mm": ok, "janela_h": 0}).status_code == 422
    assert client.post("/api/simulacao", json={"chuva_mm": ok, "janela_h": 25}).status_code == 422
    assert client.post("/api/simulacao", json={"chuva_mm": {}, "janela_h": 6}).status_code == 422
    assert client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": -1}}).status_code == 422
    assert client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": 401}}).status_code == 422
    assert client.post("/api/simulacao", json={"chuva_mm": ok, "estacao": "XXX"}).status_code == 404


def test_simulacao_sem_modelo_diz_indisponivel(client: TestClient, base: Session) -> None:
    r = client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": 50}}).json()
    assert all(not h["disponivel"] for h in r["horizontes"])


def test_estacao_inexistente_da_404(client: TestClient, base: Session) -> None:
    assert client.get("/api/previsao/XXX").status_code == 404


# --- chuva estimada: ponto sem leitura por algumas horas (so na inferencia) ---

VITOR = "DCSC-00036"


def _series_reais(
    lacuna_h: int, ponto: str = VITOR, tambem_sem: tuple[str, ...] = ()
) -> tuple[dict, dict]:
    """8 dias de chuva e nivel por hora ate AGORA; `ponto` (Vitor Meireles) sem leitura nas ultimas
    horas."""
    rng = np.random.default_rng(7)
    fim = pd.Timestamp(AGORA)
    idx = pd.date_range(end=fim, periods=24 * 8, freq="1h", tz="UTC")
    chuva = {
        c: pd.Series(np.where(rng.random(len(idx)) < 0.1, rng.gamma(2.0, 2.0, len(idx)), 0.0), idx)
        for c in PONTOS_CHUVA
    }
    for cod in (ponto, *tambem_sem):
        chuva[cod].iloc[len(idx) - lacuna_h :] = np.nan
    nivel_base = pd.Series(2.0 + 0.01 * np.arange(len(idx)), idx)
    nivel = {
        "DCSC-00043": nivel_base,
        "DCSC-00021": nivel_base * 1.1,
        "DCSC-00020": nivel_base,
        "DCSC-00174": nivel_base * 0.8,
    }
    return chuva, nivel


def _com_series(
    monkeypatch: pytest.MonkeyPatch,
    lacuna_h: int,
    nivel_sem_h: int = 0,
    ponto: str = VITOR,
    tambem_sem: tuple[str, ...] = (),
    boiteux_sem_h: int = 0,
) -> None:
    chuva, nivel = _series_reais(lacuna_h, ponto, tambem_sem)
    if nivel_sem_h:
        nivel["DCSC-00043"].iloc[-nivel_sem_h:] = np.nan
    if boiteux_sem_h:  # Boiteux: nivel e chuva sem leitura nas ultimas horas
        nivel["DCSC-00021"].iloc[-boiteux_sem_h:] = np.nan
        chuva["DCSC-00021"].iloc[-boiteux_sem_h:] = np.nan
    monkeypatch.setattr("api.previsao.chuva_horaria", lambda s, c, ini, fim: chuva[c])
    monkeypatch.setattr("api.previsao.nivel_horario", lambda s, c, ini, fim: nivel[c])


def test_lacuna_pequena_de_um_ponto_de_chuva_ainda_estima_e_avisa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, extras=(VITOR,))  # o modelo usa a chuva da Vitor
    _com_series(monkeypatch, lacuna_h=14)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is True and tres["nivel_m"] is not None
    assert r["chuva_estimada"] == [{"codigo": VITOR, "nome": "PCD Vitor Meireles", "horas": 14}]
    # a simulacao passa pelo mesmo caminho e traz o mesmo aviso
    sim = client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": 10}}).json()
    assert sim["origem"] == "cenario" and sim["chuva_estimada"][0]["horas"] == 14


def test_lacuna_acima_do_limite_continua_sem_estimativa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, extras=(VITOR,))
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 1)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is False and "Sem dados recentes" in tres["motivo"]
    assert r["chuva_estimada"] == []


def test_sem_lacuna_nao_mostra_chuva_estimada(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)
    _com_series(monkeypatch, lacuna_h=0)
    r = client.get("/api/previsao/DCSC-00043").json()
    assert next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True
    assert r["chuva_estimada"] == []


def test_ponto_que_o_modelo_nao_usa_fora_do_ar_nao_derruba_nem_gera_aviso(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)  # usa so a chuva local e a de Dona Emma
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=VITOR)
    r = client.get("/api/previsao/DCSC-00043").json()
    assert next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True
    assert r["chuva_estimada"] == []


def test_aviso_so_lista_ponto_estimado_que_o_modelo_usa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)  # nao usa a Vitor
    _com_series(monkeypatch, lacuna_h=14, ponto=VITOR)
    r = client.get("/api/previsao/DCSC-00043").json()
    assert next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True
    assert r["chuva_estimada"] == []  # a linha e toda medida nas colunas do modelo


def test_nivel_nunca_e_estimado(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)
    _com_series(monkeypatch, lacuna_h=0, nivel_sem_h=5)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is False and r["chuva_estimada"] == []


# --- pontos novos (serras) e Revolver ---

SERRA = "DC-PEU-004"
REVOLVER = "DCSC-00174"


def _todas_as_colunas(estacao: str) -> list[str]:
    """Colunas de um modelo hipotetico que usa TODAS as variaveis do alvo."""
    q = montar_quadros(None, estacao, AGORA)  # type: ignore[arg-type]
    assert q is not None
    return list(q.medido.columns)


def test_serra_nunca_entra_nas_variaveis_do_rio_dos_indios(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serra fora do ar nao afeta o Indios: ela nem faz parte das variaveis desse alvo."""
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=SERRA)
    colunas = _todas_as_colunas("DCSC-00043")
    assert not any("serra" in c or "revolver" in c for c in colunas)
    q = montar_quadros(None, "DCSC-00043", AGORA)  # type: ignore[arg-type]
    achada = escolher_linha(q, colunas, AGORA)  # type: ignore[arg-type]
    assert achada is not None and achada[1] == pd.Timestamp(AGORA) and achada[2] == {}


def test_ponto_antigo_fora_do_ar_continua_sem_estimativa(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=VITOR)
    q = montar_quadros(None, "DCSC-00043", AGORA)  # type: ignore[arg-type]
    assert escolher_linha(q, _todas_as_colunas("DCSC-00043"), AGORA) is None  # type: ignore[arg-type]


def test_lacuna_pequena_de_serra_e_estimada_como_qualquer_ponto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _com_series(monkeypatch, lacuna_h=5, ponto=SERRA)
    q = montar_quadros(None, REVOLVER, AGORA)  # type: ignore[arg-type]
    achada = escolher_linha(q, _todas_as_colunas(REVOLVER), AGORA)  # type: ignore[arg-type]
    assert achada is not None and achada[2] == {SERRA: 5}


def test_serra_fora_do_ar_nao_afeta_o_modelo_que_nao_a_usa_e_o_que_usa_fica_sem_dados(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, codigo=REVOLVER)  # sem colunas de serra
    _publicar(base, tmp_path, 6, codigo=REVOLVER, com_serras=True)  # exige a serra
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=SERRA)
    r = client.get(f"/api/previsao/{REVOLVER}").json()
    h = {x["horizonte_h"]: x for x in r["horizontes"]}
    assert h[3]["disponivel"] is True and h[3]["nivel_m"] is not None
    assert h[6]["disponivel"] is False and "Sem dados recentes" in h[6]["motivo"]
    assert r["base_em"] is not None and r["nivel_base_m"] is not None


def test_boiteux_com_lacuna_nao_derruba_o_revolver_mas_derruba_o_indios(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, codigo=REVOLVER)  # nao usa Boiteux
    _publicar(base, tmp_path, 3, codigo="DCSC-00043")  # usa o nivel de Boiteux (remanso)
    _com_series(monkeypatch, lacuna_h=0, boiteux_sem_h=30)
    revolver = client.get(f"/api/previsao/{REVOLVER}").json()
    indios = client.get("/api/previsao/DCSC-00043").json()
    assert next(h for h in revolver["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True
    ind3 = next(h for h in indios["horizontes"] if h["horizonte_h"] == 3)
    assert ind3["disponivel"] is False and "Sem dados recentes" in ind3["motivo"]


def test_horizontes_diferentes_usam_linhas_diferentes(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serras sem dado nas 2 ultimas horas (e sem vizinhos para estimar): o modelo que as usa
    fica com a hora de 2 h atras; o que nao as usa, com a hora mais recente."""
    _publicar(base, tmp_path, 3, codigo=REVOLVER)
    _publicar(base, tmp_path, 6, codigo=REVOLVER, com_serras=True)
    _com_series(
        monkeypatch,
        lacuna_h=2,
        ponto="DC-PEU-003",
        tambem_sem=("DC-PEU-004", "DC-PEU-002", REVOLVER),
    )
    r = client.get(f"/api/previsao/{REVOLVER}").json()
    h = {x["horizonte_h"]: x for x in r["horizontes"]}
    agora = pd.Timestamp(AGORA)
    assert h[3]["disponivel"] and h[6]["disponivel"]
    assert pd.Timestamp(h[3]["valido_para"]) == agora + pd.Timedelta(hours=3)
    assert pd.Timestamp(h[6]["valido_para"]) == agora - pd.Timedelta(hours=2) + pd.Timedelta(
        hours=6
    )
    assert pd.Timestamp(r["base_em"]) == agora  # a base e a hora mais recente usada
    assert r["chuva_estimada"] == []


def test_revolver_e_servido_quando_ha_modelo_publicado(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, linha = _publicar(base, tmp_path, 3, codigo=REVOLVER)
    _com_linha(monkeypatch, linha)
    r = client.get(f"/api/previsao/{REVOLVER}").json()
    assert r["estacao"] == REVOLVER
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is True and tres["nivel_m"] is not None
    # o rio dos Indios continua sem modelo: nada vaza de um alvo para o outro
    outro = client.get("/api/previsao/DCSC-00043").json()
    assert not any(h["disponivel"] for h in outro["horizontes"])
    sim = client.post(
        "/api/simulacao", json={"estacao": REVOLVER, "chuva_mm": {REVOLVER: 40, "DCSC-00043": 40}}
    ).json()
    assert sim["origem"] == "cenario" and sim["estacao"] == REVOLVER


def test_revolver_sem_modelo_diz_indisponivel(client: TestClient, base: Session) -> None:
    r = client.get(f"/api/previsao/{REVOLVER}")
    assert r.status_code == 200
    assert not any(h["disponivel"] for h in r.json()["horizontes"])


def test_linha_do_revolver_usa_o_nivel_do_revolver(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_series(monkeypatch, lacuna_h=0)
    q = montar_quadros(None, REVOLVER, AGORA)  # type: ignore[arg-type]
    achada = escolher_linha(q, _todas_as_colunas(REVOLVER), AGORA)  # type: ignore[arg-type]
    assert achada is not None
    linha, _, _ = achada
    assert linha["nivel_m"] == pytest.approx(linha["nivel_getulio_m"] * 0.8)
    assert "nivel_boiteux_m" not in linha.index
