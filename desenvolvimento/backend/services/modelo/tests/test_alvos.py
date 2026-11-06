"""Novos pontos de chuva (serras), alvo Revolver, compatibilidade com artefato antigo,
janela de treino e isolamento de falha no agendador."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from modelo import agendador
from modelo.features import (
    ALVOS,
    PONTOS_CHUVA,
    alvo_deslocado,
    montar_features,
    pontos_chuva,
    vizinhos_nivel,
)
from modelo.inferencia import (
    aplicar_cenario,
    colunas_faltando,
    extrapola,
    imputar_chuva,
    prever_variacao_cm,
)
from modelo.treinar import (
    INICIO_HISTORICO,
    cobertura,
    inicio_da_janela,
    manter_pontos_cobertos,
)
from modelo.treino import avaliar_horizonte

SERRAS = {
    "DC-PEU-003": "serra_indios",
    "DC-PEU-004": "serra_vencida",
    "DC-PEU-002": "serra_mirador",
}
REVOLVER = "DCSC-00174"
PG = "DCSC-00043"


def idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-07-01", periods=n, freq="1h", tz="UTC")


def mundo(n: int = 24 * 120, semente: int = 3):
    """Chuva em todos os pontos (as serras chovem mais), nivel do PG, do Revolver e vizinhos.

    A chuva e frequente (30% das horas): o gradient boosting minimiza o erro absoluto e, com
    chuva rara, aprenderia a variacao mediana (zero) e empataria com a persistencia.
    """
    rng = np.random.default_rng(semente)

    def chuva(escala: float) -> pd.Series:
        return pd.Series(
            np.where(rng.random(n) < 0.3, rng.gamma(2.0, 3.0 * escala, n), 0.0), idx(n)
        )

    c = {cod: chuva(1.0) for cod in PONTOS_CHUVA}
    for cod in SERRAS:
        c[cod] = chuva(1.5)
    # o Revolver responde rapido (1 h) a chuva local; o PG, em 2 h, a PG e a serra dos Indios
    resp_r = np.zeros(n)
    resp_r[1:] = c[REVOLVER].to_numpy()[: n - 1] * 0.03
    resp_p = np.zeros(n)
    resp_p[2:] = (c[PG] + c["DC-PEU-003"]).to_numpy()[: n - 2] * 0.02

    def com_recessao(resposta: np.ndarray, base: float) -> pd.Series:
        """Nivel que sobe com a chuva e volta ao normal (recessao): fica sempre limitado."""
        v = np.empty(n)
        v[0] = base
        for i in range(1, n):
            v[i] = v[i - 1] + resposta[i] - 0.15 * (v[i - 1] - base)
        return pd.Series(v, idx(n))

    nivel_r = com_recessao(resp_r, 1.0)
    nivel_p = com_recessao(resp_p, 1.5)
    nivel = {
        PG: nivel_p,
        REVOLVER: nivel_r,
        "DCSC-00021": nivel_p * 1.1,
        "DCSC-00020": nivel_p * 0.9,
    }
    return c, nivel


# ---------- serras ----------


def test_serras_entram_nos_pontos_de_chuva_com_rotulos_curtos() -> None:
    for cod, rotulo in SERRAS.items():
        assert PONTOS_CHUVA[cod] == rotulo
    assert {REVOLVER, *SERRAS} <= set(PONTOS_CHUVA)


# ---------- pontos de chuva por alvo ----------

PONTOS_ANTIGOS = {
    "DCSC-00043": "local",
    "DCSC-00037": "emma",
    "DCSC-00021": "boiteux",
    "DCSC-00015": "witmarsum",
    "DCSC-00036": "vitor",
}


PONTOS_PG = {
    "DCSC-00043": "local",
    "DCSC-00037": "emma",
    "DCSC-00015": "witmarsum",
    "DCSC-00174": "revolver",
    **SERRAS,
}


def test_pg_usa_o_conjunto_novo_com_serras_e_revolver_sem_boiteux_nem_vitor() -> None:
    assert pontos_chuva(PG) == PONTOS_PG
    assert list(pontos_chuva(PG)) == [
        "DCSC-00043",
        "DCSC-00037",
        "DCSC-00015",
        "DCSC-00174",
        "DC-PEU-003",
        "DC-PEU-004",
        "DC-PEU-002",
    ]  # mesma ordem das colunas
    assert set(ALVOS[PG].pontos_chuva) == set(PONTOS_PG)
    assert "DCSC-00021" not in PONTOS_PG and "DCSC-00036" not in PONTOS_PG


def test_revolver_usa_local_revolver_e_serras_sem_emma_nem_witmarsum() -> None:
    assert pontos_chuva(REVOLVER) == {
        PG: "local",
        REVOLVER: "revolver",
        **SERRAS,
    }


def test_alvo_desconhecido_usa_o_conjunto_padrao() -> None:
    assert pontos_chuva("DCSC-99999") == PONTOS_ANTIGOS


def test_colunas_do_pg_sao_as_do_conjunto_novo_e_nao_ganham_pontos_so_por_existirem() -> None:
    """mundo() traz tambem Boiteux e Vitor: o PG nao os usa, nem como chuva nem como nivel."""
    c, nivel = mundo(24 * 20)
    X = montar_features(c, nivel)
    assert not any(
        "boiteux" in col or "vitor" in col or "ibirama" in col for col in X.columns
    )  # nem chuva, nem nivel de vizinho, nem as interacoes
    esperadas = {
        f"chuva_{r}_{j}h" for r in PONTOS_PG.values() for j in (1, 3, 6, 12, 24, 48, 72, 168)
    }
    assert esperadas <= set(X.columns)
    assert len([col for col in X.columns if col.startswith("chuva_")]) == len(esperadas)
    assert "emma_x_boiteux_6h" not in X.columns and "ibirama_x_chuva_local_3h" not in X.columns
    # so o nivel do proprio alvo: nenhuma coluna de nivel de vizinho
    assert [col for col in X.columns if col.startswith("nivel_")] == [
        "nivel_m",
        "nivel_min_24h_m",
        "nivel_max_24h_m",
    ]
    pd.testing.assert_frame_equal(
        X, montar_features({k: v for k, v in c.items() if k in PONTOS_PG}, nivel)
    )


def test_features_trazem_todas_as_janelas_das_serras() -> None:
    c, nivel = mundo(24 * 20)
    X = montar_features(c, nivel, alvo=REVOLVER)
    for rotulo in SERRAS.values():
        for j in (1, 3, 6, 12, 24, 48, 72, 168):
            assert f"chuva_{rotulo}_{j}h" in X.columns


def test_estacao_fora_de_alvos_continua_com_o_conjunto_e_as_interacoes_de_antes() -> None:
    c, nivel = mundo(24 * 20)
    so_antigas = {k: v for k, v in c.items() if k in PONTOS_ANTIGOS}
    desconhecida = {"DCSC-99999": nivel[PG], "DCSC-00021": nivel["DCSC-00021"]}
    desconhecida["DCSC-00020"] = nivel["DCSC-00020"]
    X = montar_features(so_antigas, desconhecida, alvo="DCSC-99999")
    assert not any("serra" in col or "revolver" in col for col in X.columns)
    assert "emma_x_boiteux_6h" in X.columns and "ibirama_x_chuva_local_3h" in X.columns


def test_features_com_serras_nao_enxergam_o_futuro() -> None:
    c, nivel = mundo(24 * 20)
    t = 24 * 15
    completo = montar_features(c, nivel, alvo=REVOLVER)
    cortado = montar_features(
        {k: v.iloc[: t + 1] for k, v in c.items()},
        {k: v.iloc[: t + 1] for k, v in nivel.items()},
        alvo=REVOLVER,
    )
    pd.testing.assert_series_equal(completo.iloc[t], cortado.iloc[t], check_names=False)
    adulterado = {k: v.copy() for k, v in c.items()}
    for v in adulterado.values():
        v.iloc[t + 1 :] = 500.0
    f2 = montar_features(adulterado, nivel, alvo=REVOLVER)
    pd.testing.assert_series_equal(completo.iloc[t], f2.iloc[t], check_names=False)


# ---------- alvo Revolver ----------


def test_cada_alvo_tem_config_e_nunca_usa_o_proprio_nivel_como_vizinho() -> None:
    assert set(ALVOS) == {PG, REVOLVER}
    for cod in ALVOS:
        assert cod not in vizinhos_nivel(cod)
    assert vizinhos_nivel(REVOLVER) == {PG: "getulio"}
    assert vizinhos_nivel(PG) == {}  # Boiteux e Ibirama saíram do 00043 (ADR 0006)
    assert vizinhos_nivel("DCSC-99999") == {"DCSC-00021": "boiteux", "DCSC-00020": "ibirama"}


def test_features_do_revolver_usam_o_nivel_do_revolver_e_o_do_rio_dos_indios() -> None:
    c, nivel = mundo(24 * 20)
    X = montar_features(c, nivel, alvo=REVOLVER)
    pd.testing.assert_series_equal(X["nivel_m"], nivel[REVOLVER], check_names=False)
    pd.testing.assert_series_equal(X["nivel_getulio_m"], nivel[PG], check_names=False)
    assert "taxa_getulio_1h_cm" in X.columns
    # nivel de Boiteux/Ibirama e as interacoes do rio grande ficam de fora
    assert not [col for col in X.columns if "boiteux_m" in col or "ibirama" in col]
    assert "emma_x_boiteux_6h" not in X.columns
    assert "chuva_revolver_3h" in X.columns and "chuva_serra_indios_1h" in X.columns


def test_alvo_nunca_aparece_como_vizinho_de_si_mesmo() -> None:
    c, nivel = mundo(24 * 20)
    X = montar_features(c, nivel, alvo=PG)
    assert "nivel_getulio_m" not in X.columns  # PG e o alvo: so `nivel_m`
    X2 = montar_features(
        c, nivel, alvo="DCSC-00021"
    )  # alvo fora de ALVOS: vizinho padrao menos ele
    assert "nivel_boiteux_m" not in X2.columns and "nivel_ibirama_m" in X2.columns


def test_alvo_pg_nao_muda_com_o_nivel_do_revolver_no_dicionario() -> None:
    c, nivel = mundo(24 * 20)
    sem = {k: v for k, v in nivel.items() if k != REVOLVER}
    pd.testing.assert_frame_equal(montar_features(c, nivel), montar_features(c, sem))


def test_revolver_aprende_e_vence_a_persistencia_com_dados_sinteticos() -> None:
    c, nivel = mundo()
    X = montar_features(c, nivel, alvo=REVOLVER)
    r = avaliar_horizonte(X, alvo_deslocado(nivel[REVOLVER], 3), 3)
    assert r.publicar, r.motivo
    assert "chuva_revolver_1h" in r.colunas


# ---------- inferencia: artefato antigo x novo ----------


def artefato(c, nivel, colunas_fora: tuple[str, ...] = ("serra",), alvo: str = REVOLVER):
    """Treina um artefato; `colunas_fora` tira as colunas com esses trechos (modelo antigo)."""
    X = montar_features(c, nivel, alvo=alvo)
    X = X[[col for col in X.columns if not any(t in col for t in colunas_fora)]]
    r = avaliar_horizonte(X, alvo_deslocado(nivel[alvo], 3), 3)
    assert r.pipeline is not None
    return {"pipeline": r.pipeline, "colunas": r.colunas, "faixa_treino": r.faixa_treino}


def test_modelo_sem_as_serras_continua_funcionando_com_linha_que_as_tem() -> None:
    c, nivel = mundo()
    antigo = artefato(c, nivel)
    assert not any("serra" in col for col in antigo["colunas"])
    linha = montar_features(c, nivel, alvo=REVOLVER).dropna().iloc[-1]  # linha com as serras
    assert colunas_faltando(antigo, linha) == []
    assert np.isfinite(prever_variacao_cm(antigo, linha))
    assert extrapola(antigo, linha) == []
    # a simulacao tambem: cenario com chuva numa serra nao quebra o modelo
    cenario = aplicar_cenario(linha, {REVOLVER: 10.0, "DC-PEU-003": 30.0}, 6, alvo=REVOLVER)
    assert np.isfinite(prever_variacao_cm(antigo, cenario))
    assert cenario["chuva_serra_indios_6h"] == pytest.approx(30.0)


def test_cenario_do_pg_aplica_serras_e_revolver_e_ignora_pontos_que_nao_sao_do_alvo() -> None:
    c, nivel = mundo()
    linha = montar_features(c, nivel).dropna().iloc[-1]  # alvo PG: com serras e Revolver
    cenario = aplicar_cenario(linha, {PG: 10.0, "DC-PEU-003": 30.0, REVOLVER: 5.0}, 6, alvo=PG)
    assert cenario["chuva_local_6h"] == pytest.approx(10.0)
    assert cenario["chuva_serra_indios_6h"] == pytest.approx(30.0)
    assert cenario["chuva_revolver_6h"] == pytest.approx(5.0)
    # com `alvo`, um ponto que nao e do alvo (Vitor) e ignorado mesmo que a linha tenha a coluna
    com_vitor = linha.copy()
    com_vitor["chuva_vitor_6h"] = 1.0
    nova = aplicar_cenario(com_vitor, {"DCSC-00036": 30.0}, 6, alvo=PG)
    assert nova["chuva_vitor_6h"] == 1.0


def test_modelo_antigo_ignora_serra_sem_dado_mas_o_novo_recusa() -> None:
    c, nivel = mundo()
    antigo, novo = artefato(c, nivel), artefato(c, nivel, colunas_fora=())
    linha = montar_features(c, nivel, alvo=REVOLVER).dropna().iloc[-1].copy()
    linha["chuva_serra_vencida_3h"] = np.nan  # serra fora do ar agora
    assert colunas_faltando(antigo, linha) == []
    assert np.isfinite(prever_variacao_cm(antigo, linha))
    assert colunas_faltando(novo, linha) == ["chuva_serra_vencida_3h"]


def test_modelo_novo_exige_as_colunas_ausentes_da_linha() -> None:
    c, nivel = mundo()
    novo = artefato(c, nivel, colunas_fora=())
    sem_serras = montar_features({k: v for k, v in c.items() if k not in SERRAS}, nivel, REVOLVER)
    linha = sem_serras.dropna().iloc[-1]
    faltam = colunas_faltando(novo, linha)
    assert faltam and all("serra" in col for col in faltam)


def test_modelo_do_revolver_previsao_sobe_com_chuva_local() -> None:
    c, nivel = mundo()
    art = artefato(c, nivel, colunas_fora=())
    X = montar_features(c, nivel, alvo=REVOLVER)
    linha = X.dropna().iloc[-1]
    seco = aplicar_cenario(linha, {REVOLVER: 0.0, PG: 0.0}, 3)
    chuvoso = aplicar_cenario(linha, {REVOLVER: 30.0, PG: 30.0}, 3)
    assert prever_variacao_cm(art, chuvoso) > prever_variacao_cm(art, seco)


def test_imputacao_trata_as_serras_como_pontos_comuns() -> None:
    c, _ = mundo(72)
    c["DC-PEU-004"] = c["DC-PEU-004"].copy()
    c["DC-PEU-004"].iloc[-5:] = np.nan
    novo, horas = imputar_chuva(c)
    assert novo["DC-PEU-004"].notna().all() and len(horas["DC-PEU-004"]) == 5


# ---------- janela de treino e cobertura ----------


def test_janela_padrao_e_por_alvo_e_argumentos_sobrescrevem() -> None:
    fim = datetime(2026, 11, 5, 12, tzinfo=UTC)
    assert date(2025, 9, 13) == INICIO_HISTORICO
    assert ALVOS[PG].janela_dias is None  # todo o historico (sem Boiteux/Ibirama, ADR 0006)
    assert ALVOS[REVOLVER].janela_dias is None  # todo o historico do painel
    # padrao de cada alvo: ambos desde o inicio do historico do painel
    for alvo in (PG, REVOLVER):
        assert inicio_da_janela(fim, padrao_dias=ALVOS[alvo].janela_dias) == datetime(
            2025, 9, 13, tzinfo=UTC
        )
    # --dias / --desde sobrescrevem o padrao do alvo
    assert inicio_da_janela(fim, dias=30, padrao_dias=120) == fim - timedelta(days=30)
    assert inicio_da_janela(fim, desde=date(2026, 1, 1), padrao_dias=120) == datetime(
        2026, 1, 1, tzinfo=UTC
    )
    assert inicio_da_janela(fim, dias=30, desde=date(2026, 1, 1)) == fim - timedelta(days=30)


def test_ponto_com_pouca_cobertura_e_deixado_de_fora_mas_o_alvo_nao() -> None:
    ini = datetime(2026, 7, 1, tzinfo=UTC)
    fim = ini + timedelta(days=10)
    completo = pd.Series(1.0, idx(240))
    curto = completo.copy()
    curto.iloc[:200] = np.nan  # 17% de cobertura
    vazio = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    assert cobertura(completo, ini, fim) == 1.0
    mantidos, fora = manter_pontos_cobertos(
        {"a": completo, "b": curto, "c": vazio, "alvo": curto}, ini, fim, obrigatorios=("alvo",)
    )
    assert set(mantidos) == {"a", "alvo"} and set(fora) == {"b", "c"}
    assert fora["b"] == pytest.approx(0.167, abs=1e-3) and fora["c"] == 0.0


# ---------- agendador: um alvo nao derruba o outro ----------


def test_falha_em_um_alvo_nao_impede_o_treino_do_outro(monkeypatch) -> None:
    chamados: list[str] = []

    def falso(alvo, dias=None, salvar=True, desde=None):
        chamados.append(alvo)
        if alvo == PG:
            raise RuntimeError("banco caiu")
        return []

    monkeypatch.setattr(agendador, "treinar", falso)
    assert agendador.rodar() == {PG: False, REVOLVER: True}
    assert chamados == [PG, REVOLVER]


def test_alvo_sem_leituras_nao_impede_o_outro(monkeypatch) -> None:
    from modelo.treinar import TreinoImpossivel

    def falso(alvo, dias=None, salvar=True, desde=None):
        if alvo == REVOLVER:
            raise TreinoImpossivel("sem leituras de nivel")
        return []

    monkeypatch.setattr(agendador, "treinar", falso)
    assert agendador.rodar() == {PG: True, REVOLVER: False}


def test_agendador_repassa_a_janela(monkeypatch) -> None:
    recebido = []
    monkeypatch.setattr(
        agendador,
        "treinar",
        lambda alvo, dias=None, salvar=True, desde=None: (
            recebido.append((alvo, dias, salvar, desde)) or []
        ),
    )
    agendador.rodar(dias=200)
    agendador.rodar(alvos=(REVOLVER,), desde=date(2026, 1, 1))
    assert recebido == [
        (PG, 200, True, None),
        (REVOLVER, 200, True, None),
        (REVOLVER, None, True, date(2026, 1, 1)),
    ]
