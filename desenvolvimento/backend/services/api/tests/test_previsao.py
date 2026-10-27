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


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-07-01", periods=n, freq="1h", tz="UTC")


def _treinar_artefato(horizonte: int = 3):
    rng = np.random.default_rng(1)
    n = 24 * 120
    chuva = pd.Series(np.where(rng.random(n) < 0.08, rng.gamma(2.0, 3.0, n), 0.0), _idx(n))
    resposta = np.zeros(n)
    resposta[2:] = chuva.to_numpy()[: n - 2] * 0.02
    nivel = pd.Series(1.0 + np.cumsum(resposta - 0.003), _idx(n)).clip(lower=0.5)
    X = montar_features(
        {"DCSC-00043": chuva, "DCSC-00037": chuva.shift(1).fillna(0)},
        {"DCSC-00043": nivel, "DCSC-00021": nivel * 1.1, "DCSC-00020": nivel * 0.9},
    )
    r = avaliar_horizonte(X, alvo_deslocado(nivel, horizonte), horizonte)
    return r, X.dropna().iloc[-1]


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def _est(s: Session) -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one()


def _publicar(s: Session, tmp: Path, horizonte: int = 3) -> tuple[Modelo, pd.Series]:
    r, linha = _treinar_artefato(horizonte)
    assert r.pipeline is not None
    caminho = tmp / f"m{horizonte}.joblib"
    joblib.dump(
        {"pipeline": r.pipeline, "colunas": r.colunas, "faixa_treino": r.faixa_treino}, caminho
    )
    m = Modelo(
        estacao_id=_est(s).id,
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


def _com_linha(
    monkeypatch: pytest.MonkeyPatch,
    linha: pd.Series | None,
    estimadas: dict[str, int] | None = None,
) -> None:
    resultado = (
        (linha, pd.Timestamp(AGORA - timedelta(hours=1)), estimadas or {})
        if linha is not None
        else None
    )
    monkeypatch.setattr("api.previsao.linha_atual", lambda s, estacao, agora: resultado)


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


def _series_reais(lacuna_h: int) -> tuple[dict, dict]:
    """8 dias de chuva e nivel por hora ate AGORA; Vitor Meireles sem leitura nas ultimas horas."""
    rng = np.random.default_rng(7)
    fim = pd.Timestamp(AGORA)
    idx = pd.date_range(end=fim, periods=24 * 8, freq="1h", tz="UTC")
    chuva = {
        c: pd.Series(np.where(rng.random(len(idx)) < 0.1, rng.gamma(2.0, 2.0, len(idx)), 0.0), idx)
        for c in PONTOS_CHUVA
    }
    chuva[VITOR].iloc[len(idx) - lacuna_h :] = np.nan
    nivel_base = pd.Series(2.0 + 0.01 * np.arange(len(idx)), idx)
    nivel = {"DCSC-00043": nivel_base, "DCSC-00021": nivel_base * 1.1, "DCSC-00020": nivel_base}
    return chuva, nivel


def _com_series(monkeypatch: pytest.MonkeyPatch, lacuna_h: int, nivel_sem_h: int = 0) -> None:
    chuva, nivel = _series_reais(lacuna_h)
    if nivel_sem_h:
        nivel["DCSC-00043"].iloc[-nivel_sem_h:] = np.nan
    monkeypatch.setattr("api.previsao.chuva_horaria", lambda s, c, ini, fim: chuva[c])
    monkeypatch.setattr("api.previsao.nivel_horario", lambda s, c, ini, fim: nivel[c])


def test_lacuna_pequena_de_um_ponto_de_chuva_ainda_estima_e_avisa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)
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
    _publicar(base, tmp_path, 3)
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


def test_nivel_nunca_e_estimado(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)
    _com_series(monkeypatch, lacuna_h=0, nivel_sem_h=5)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is False and r["chuva_estimada"] == []
