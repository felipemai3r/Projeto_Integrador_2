import functools
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
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.orm import Session
from tempo_api import AGORA

from api.previsao import Quadros, escolher_linha, montar_quadros


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-07-01", periods=n, freq="1h", tz="UTC")


@functools.cache  # o treino e o trecho caro dos testes; o resultado nao e alterado por ninguem
def _treinar_artefato(
    horizonte: int = 3,
    alvo: str = "DCSC-00043",
    com_serras: bool = False,
    extras: tuple[str, ...] = (),
):
    rng = np.random.default_rng(1)
    n = 24 * 120
    # chuva frequente: o gradient boosting (perda absoluta) so aprende a relacao se ela for tipica
    chuva = pd.Series(np.where(rng.random(n) < 0.3, rng.gamma(2.0, 3.0, n), 0.0), _idx(n))
    resposta = np.zeros(n)
    resposta[2:] = chuva.to_numpy()[: n - 2] * 0.03
    v = np.empty(n)
    v[0] = 1.0
    for i in range(1, n):  # sobe com a chuva e volta ao normal (recessao): fica limitado
        v[i] = v[i - 1] + resposta[i] - 0.15 * (v[i - 1] - 1.0)
    nivel = pd.Series(v, _idx(n))
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
    antigo: bool = False,
) -> tuple[Modelo, pd.Series]:
    """Publica um modelo treinado de verdade. `antigo` grava so o que um artefato Ridge gravava
    (sem `aceita_nan` nem `intervalo_por_regime`): a API deve trata-lo como sempre."""
    r, linha = _treinar_artefato(horizonte, codigo, com_serras, extras)
    assert r.pipeline is not None
    caminho = tmp / f"m{codigo}_{horizonte}.joblib"
    artefato = {"pipeline": r.pipeline, "colunas": r.colunas, "faixa_treino": r.faixa_treino}
    metadados = {"desvio_residual_cm": r.desvio_residual_cm or 1.0, "motivo": "ok"}
    if not antigo:
        artefato |= {
            "colunas_obrigatorias": r.colunas_obrigatorias,
            "aceita_nan": r.aceita_nan,
            "intervalo_por_regime": r.intervalo_por_regime,
            "alfa_intervalo": r.alfa_intervalo,
        }
        metadados |= {
            "intervalo_por_regime": r.intervalo_por_regime,
            "alfa_intervalo": r.alfa_intervalo,
            "cobertura_validacao": r.cobertura_validacao,
            "colunas_obrigatorias": r.colunas_obrigatorias,
            "aceita_nan": r.aceita_nan,
        }
    joblib.dump(artefato, caminho)
    m = Modelo(
        estacao_id=_est(s, codigo).id,
        horizonte_h=horizonte,
        algoritmo="ridge" if antigo else "hist_gradient_boosting",
        treinado_em=AGORA,
        amostras=r.amostras,
        rmse_cm=r.rmse_cm or 1.0,
        mae_cm=1.0,
        rmse_persistencia_cm=r.rmse_persistencia_cm or 2.0,
        publicado=True,
        caminho_artefato=str(caminho),
        metadados=metadados,
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


def test_artefato_ridge_antigo_segue_igual_na_api(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compatibilidade: artefato do Ridge (sem `aceita_nan`, `colunas_obrigatorias` nem
    `intervalo_por_regime`) mantem o intervalo +-1,96 sigma e a exigencia de TODAS as colunas."""
    rng = np.random.default_rng(3)
    colunas = ["nivel_m", "taxa_1h_cm", "taxa_3h_cm_h", "chuva_local_6h"]
    X = pd.DataFrame(rng.normal(size=(300, 4)), columns=colunas)
    ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=(0.1, 1.0, 10.0))).fit(
        X, 5.0 * X["chuva_local_6h"]
    )
    caminho = tmp_path / "ridge.joblib"
    faixa = {c: (float(X[c].min()), float(X[c].max())) for c in colunas}
    joblib.dump({"pipeline": ridge, "colunas": colunas, "faixa_treino": faixa}, caminho)
    base.add(
        Modelo(
            estacao_id=_est(base).id,
            horizonte_h=3,
            algoritmo="ridge",
            treinado_em=AGORA,
            amostras=300,
            rmse_cm=9.0,
            mae_cm=7.0,
            rmse_persistencia_cm=15.0,
            publicado=True,
            caminho_artefato=str(caminho),
            metadados={"desvio_residual_cm": 10.0, "motivo": "ok", "colunas": colunas},
        )
    )
    base.commit()
    linha = pd.Series(
        {"nivel_m": 2.0, "taxa_1h_cm": 0.1, "taxa_3h_cm_h": 0.2, "chuva_local_6h": 1.0}
    )
    _com_linha(monkeypatch, linha)
    previsto = 2.0 + float(ridge.predict(linha.to_frame().T.astype(float))[0]) / 100
    tres = next(
        h
        for h in client.get("/api/previsao/DCSC-00043").json()["horizontes"]
        if h["horizonte_h"] == 3
    )
    assert tres["disponivel"] is True and tres["nivel_m"] == round(previsto, 2)
    assert tres["incerteza_m"] == 0.2  # 1,96 * 10 cm
    assert tres["confianca"] == 0.95  # +-1,96 sigma
    assert tres["intervalo_m"] == [round(previsto - 0.196, 2), round(previsto + 0.196, 2)]
    # todas as colunas continuam obrigatorias: uma em branco e "sem dados recentes"
    _com_linha(monkeypatch, linha.where(linha.index != "chuva_local_6h"))
    sem = next(
        h
        for h in client.get("/api/previsao/DCSC-00043").json()["horizontes"]
        if h["horizonte_h"] == 3
    )
    assert sem["disponivel"] is False and "Sem dados recentes" in sem["motivo"]


def test_modelo_novo_traz_intervalo_por_regime_pela_api(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m, linha = _publicar(base, tmp_path, 3)
    por_regime = m.metadados["intervalo_por_regime"]
    assert set(por_regime) == {"seco", "chuva", "chuva_forte"}
    _com_linha(monkeypatch, linha)
    tres = next(
        h
        for h in client.get("/api/previsao/DCSC-00043").json()["horizontes"]
        if h["horizonte_h"] == 3
    )
    lo, hi = tres["intervalo_m"]
    assert lo < tres["nivel_m"] < hi
    assert tres["incerteza_m"] == pytest.approx((hi - lo) / 2, abs=0.011)
    assert tres["confianca"] == 0.95  # 3 h: 95% (12 e 24 h usam 80%, ADR 0006)
    # uma simulacao de chuva forte nunca fica com intervalo mais estreito que a de tempo seco
    seco = client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": 0}}).json()
    forte = client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": 80}}).json()
    h_seco = next(h for h in seco["horizontes"] if h["horizonte_h"] == 3)
    h_forte = next(h for h in forte["horizontes"] if h["horizonte_h"] == 3)
    assert h_forte["incerteza_m"] >= h_seco["incerteza_m"]


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

VITOR = "DCSC-00036"  # fora do conjunto do rio dos Indios desde o ADR 0006
WITMARSUM = "DCSC-00015"


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
    _publicar(base, tmp_path, 3, extras=(WITMARSUM,))  # o modelo usa a chuva de Witmarsum
    _com_series(monkeypatch, lacuna_h=14, ponto=WITMARSUM)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is True and tres["nivel_m"] is not None
    assert r["chuva_estimada"] == [{"codigo": WITMARSUM, "nome": "PCD Witmarsum", "horas": 12}]
    # a simulacao passa pelo mesmo caminho e traz o mesmo aviso
    sim = client.post("/api/simulacao", json={"chuva_mm": {"DCSC-00043": 10}}).json()
    assert sim["origem"] == "cenario" and sim["chuva_estimada"][0]["horas"] == 12


def test_lacuna_pequena_modelo_antigo_tambem_estima_e_avisa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, extras=(WITMARSUM,), antigo=True)
    _com_series(monkeypatch, lacuna_h=14, ponto=WITMARSUM)
    r = client.get("/api/previsao/DCSC-00043").json()
    assert next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True
    assert r["chuva_estimada"] == [{"codigo": WITMARSUM, "nome": "PCD Witmarsum", "horas": 12}]


def test_lacuna_acima_do_limite_modelo_antigo_continua_sem_estimativa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, extras=(WITMARSUM,), antigo=True)  # exige todas as colunas
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 1, ponto=WITMARSUM)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is False and "Sem dados recentes" in tres["motivo"]
    assert r["chuva_estimada"] == []


def test_lacuna_acima_do_limite_modelo_novo_estima_com_nan_e_sem_aviso_de_estimativa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O modelo que aceita NaN segue estimando com a chuva de Witmarsum em branco (nunca zero);
    como nada foi estimado por vizinhos, nao ha aviso de chuva estimada."""
    _publicar(base, tmp_path, 3, extras=(WITMARSUM,))
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 1, ponto=WITMARSUM)
    r = client.get("/api/previsao/DCSC-00043").json()
    tres = next(h for h in r["horizontes"] if h["horizonte_h"] == 3)
    assert tres["disponivel"] is True and tres["nivel_m"] is not None
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
    _publicar(base, tmp_path, 3, antigo=True)  # usa so a chuva local e a de Dona Emma
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=WITMARSUM)
    r = client.get("/api/previsao/DCSC-00043").json()
    assert next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True
    assert r["chuva_estimada"] == []


def test_aviso_so_lista_ponto_estimado_que_o_modelo_usa(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3)  # nao usa Witmarsum
    _com_series(monkeypatch, lacuna_h=14, ponto=WITMARSUM)
    r = client.get("/api/previsao/DCSC-00043").json()
    assert next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True
    assert r["chuva_estimada"] == []  # a linha e toda medida nas colunas do modelo


@pytest.mark.parametrize("antigo", [False, True])
def test_nivel_nunca_e_estimado(
    client: TestClient,
    base: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    antigo: bool,
) -> None:
    _publicar(base, tmp_path, 3, antigo=antigo)  # o nivel e obrigatorio nos dois formatos
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


def test_boiteux_e_vitor_nunca_entram_nas_variaveis_do_rio_dos_indios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boiteux/Ibirama/Vitor fora do ar nao afetam o Indios: nem fazem parte das variaveis."""
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=VITOR, boiteux_sem_h=30)
    colunas = _todas_as_colunas("DCSC-00043")
    assert not any("boiteux" in c or "vitor" in c or "ibirama" in c for c in colunas)
    assert any("serra_indios" in c for c in colunas) and any("revolver" in c for c in colunas)
    q = montar_quadros(None, "DCSC-00043", AGORA)  # type: ignore[arg-type]
    achada = escolher_linha(q, colunas, AGORA)  # type: ignore[arg-type]
    # a ultima hora FECHADA em AGORA e a de AGORA - 2 h (a de AGORA - 1 h so fecha em AGORA + 1 min)
    assert achada is not None and achada[1] == pd.Timestamp(AGORA) - pd.Timedelta(hours=2)
    assert achada[2] == {}


def test_ponto_do_conjunto_fora_do_ar_derruba_so_o_modelo_antigo_que_o_usa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=WITMARSUM)
    q = montar_quadros(None, "DCSC-00043", AGORA)  # type: ignore[arg-type]
    colunas = _todas_as_colunas("DCSC-00043")
    assert escolher_linha(q, colunas, AGORA) is None  # type: ignore[arg-type]
    # modelo que aceita NaN: so as obrigatorias contam, e a hora mais recente serve
    achada = escolher_linha(q, colunas, AGORA, ["nivel_m", "taxa_1h_cm", "taxa_3h_cm_h"])  # type: ignore[arg-type]
    assert achada is not None and achada[1] == pd.Timestamp(AGORA) - pd.Timedelta(hours=2)
    assert np.isnan(achada[0]["chuva_witmarsum_1h"])  # em branco, nunca zero


def test_lacuna_pequena_de_serra_e_estimada_como_qualquer_ponto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _com_series(monkeypatch, lacuna_h=7, ponto=SERRA)
    q = montar_quadros(None, REVOLVER, AGORA)  # type: ignore[arg-type]
    achada = escolher_linha(q, _todas_as_colunas(REVOLVER), AGORA)  # type: ignore[arg-type]
    # 7 horas sem leitura no fim; a linha (ultima hora fechada) ve 5 delas
    assert achada is not None and achada[2] == {SERRA: 5}


def test_serra_fora_do_ar_nao_afeta_o_modelo_que_nao_a_usa_e_o_que_usa_fica_sem_dados(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, codigo=REVOLVER)  # sem colunas de serra
    _publicar(base, tmp_path, 6, codigo=REVOLVER, com_serras=True, antigo=True)  # exige a serra
    _com_series(monkeypatch, lacuna_h=MAX_HORAS_IMPUTADAS + 6, ponto=SERRA)
    r = client.get(f"/api/previsao/{REVOLVER}").json()
    h = {x["horizonte_h"]: x for x in r["horizontes"]}
    assert h[3]["disponivel"] is True and h[3]["nivel_m"] is not None
    assert h[6]["disponivel"] is False and "Sem dados recentes" in h[6]["motivo"]
    assert r["base_em"] is not None and r["nivel_base_m"] is not None


def test_boiteux_com_lacuna_nao_derruba_nenhum_dos_dois_alvos(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publicar(base, tmp_path, 3, codigo=REVOLVER, antigo=True)  # nao usa Boiteux
    _publicar(base, tmp_path, 3, codigo="DCSC-00043", antigo=True)  # tambem nao (ADR 0006)
    _com_series(monkeypatch, lacuna_h=0, boiteux_sem_h=30)
    for codigo in (REVOLVER, "DCSC-00043"):
        r = client.get(f"/api/previsao/{codigo}").json()
        assert next(h for h in r["horizontes"] if h["horizonte_h"] == 3)["disponivel"] is True


def test_horizontes_diferentes_usam_linhas_diferentes(
    client: TestClient, base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serras sem dado nas 3 ultimas horas (e sem vizinhos para estimar): o modelo que as usa
    fica com a hora de 3 h atras (o limite de idade); o que nao as usa, com a ultima hora
    fechada (2 h atras)."""
    _publicar(base, tmp_path, 3, codigo=REVOLVER)
    _publicar(base, tmp_path, 6, codigo=REVOLVER, com_serras=True, antigo=True)
    _com_series(
        monkeypatch,
        lacuna_h=3,
        ponto="DC-PEU-003",
        tambem_sem=("DC-PEU-004", "DC-PEU-002", REVOLVER),
    )
    r = client.get(f"/api/previsao/{REVOLVER}").json()
    h = {x["horizonte_h"]: x for x in r["horizontes"]}
    agora = pd.Timestamp(AGORA)
    assert h[3]["disponivel"] and h[6]["disponivel"]
    fechada = agora - pd.Timedelta(hours=2)  # ultima hora ja terminada em AGORA
    assert pd.Timestamp(h[3]["valido_para"]) == fechada + pd.Timedelta(hours=3)
    assert pd.Timestamp(h[6]["valido_para"]) == agora - pd.Timedelta(hours=3) + pd.Timedelta(
        hours=6
    )
    assert pd.Timestamp(r["base_em"]) == fechada  # a base e a hora mais recente usada
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
