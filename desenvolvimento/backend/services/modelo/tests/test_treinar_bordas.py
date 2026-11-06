"""Orquestracao do treino: janela, cobertura dos pontos, alvo sem dados e isolamento de falha."""

import logging
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from common.seed import semear
from sqlalchemy.orm import Session

from modelo import agendador, treinar
from modelo.features import ALVOS, HORIZONTES_H, pontos_chuva
from modelo.treinar import (
    INICIO_HISTORICO,
    MIN_COBERTURA_PONTO,
    TreinoImpossivel,
    cobertura,
    formatar,
    inicio_da_janela,
    manter_pontos_cobertos,
)
from modelo.treino import Resultado

AGORA = datetime(2026, 11, 5, 12, 30, tzinfo=UTC)
FIM = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)  # AGORA truncado para a hora
PG = "DCSC-00043"
REVOLVER = "DCSC-00174"


def horas(n: int, fim: datetime = FIM) -> pd.DatetimeIndex:
    return pd.date_range(end=fim - timedelta(hours=1), periods=n, freq="1h", tz="UTC")


# ---------- inicio_da_janela ----------


def test_inicio_sem_nenhum_argumento_e_o_inicio_do_historico_da_fonte() -> None:
    assert inicio_da_janela(FIM) == datetime(2025, 9, 13, tzinfo=UTC)
    assert date(2025, 9, 13) == INICIO_HISTORICO


def test_dias_zero_e_um_pedido_valido_e_nao_cai_no_padrao() -> None:
    assert inicio_da_janela(FIM, dias=0, padrao_dias=120) == FIM


def test_dias_vence_desde_e_o_padrao_so_vale_sem_argumentos() -> None:
    assert inicio_da_janela(FIM, dias=10, desde=date(2026, 1, 1), padrao_dias=120) == (
        FIM - timedelta(days=10)
    )
    assert inicio_da_janela(FIM, padrao_dias=120) == FIM - timedelta(days=120)
    assert inicio_da_janela(FIM, desde=date(2026, 3, 1), padrao_dias=120) == datetime(
        2026, 3, 1, tzinfo=UTC
    )


def test_desde_vira_meia_noite_utc() -> None:
    assert inicio_da_janela(FIM, desde=date(2026, 3, 1)).utcoffset() == timedelta(0)
    assert inicio_da_janela(FIM, desde=date(2026, 3, 1)).hour == 0


# ---------- cobertura ----------


def test_cobertura_conta_so_horas_da_janela_com_valor() -> None:
    ini = datetime(2026, 11, 1, tzinfo=UTC)
    serie = pd.Series(
        1.0, pd.date_range(ini - timedelta(hours=10), periods=60, freq="1h", tz="UTC")
    )
    serie.iloc[12] = np.nan
    # janela de 24 h: [ini, ini + 24h); 10 horas antes ficam de fora, 1 NaN dentro
    assert cobertura(serie, ini, ini + timedelta(hours=24)) == pytest.approx(23 / 24)


def test_cobertura_fim_exclusivo_e_inicio_inclusivo() -> None:
    ini = datetime(2026, 11, 1, tzinfo=UTC)
    serie = pd.Series(1.0, pd.date_range(ini, periods=5, freq="1h", tz="UTC"))
    assert cobertura(serie, ini, ini + timedelta(hours=4)) == 1.0  # hora 04 (== fim) fica fora
    assert cobertura(serie, ini, ini + timedelta(hours=10)) == 0.5


def test_cobertura_de_janela_menor_que_uma_hora_nao_divide_por_zero() -> None:
    ini = datetime(2026, 11, 1, tzinfo=UTC)
    serie = pd.Series([1.0], pd.DatetimeIndex([ini]))
    assert cobertura(serie, ini, ini + timedelta(minutes=10)) == 1.0


def test_pontos_com_exatamente_a_cobertura_minima_ficam_e_logo_abaixo_saem() -> None:
    ini = datetime(2026, 11, 1, tzinfo=UTC)
    fim = ini + timedelta(hours=100)
    idx = pd.date_range(ini, periods=100, freq="1h", tz="UTC")
    metade = pd.Series(np.where(np.arange(100) < 50, 1.0, np.nan), idx)
    quase = pd.Series(np.where(np.arange(100) < 49, 1.0, np.nan), idx)
    mantidos, fora = manter_pontos_cobertos({"metade": metade, "quase": quase}, ini, fim)
    assert MIN_COBERTURA_PONTO == 0.5
    assert set(mantidos) == {"metade"} and fora == {"quase": 0.49}


def test_alvo_obrigatorio_fica_mesmo_com_pouca_cobertura_mas_nao_se_estiver_vazio() -> None:
    ini = datetime(2026, 11, 1, tzinfo=UTC)
    fim = ini + timedelta(hours=100)
    pouco = pd.Series([1.0], pd.DatetimeIndex([ini]))
    vazio = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    mantidos, fora = manter_pontos_cobertos(
        {"alvo": pouco, "outro": pouco}, ini, fim, obrigatorios=("alvo",)
    )
    assert set(mantidos) == {"alvo"} and fora == {"outro": 0.01}
    mantidos, fora = manter_pontos_cobertos({"alvo": vazio}, ini, fim, obrigatorios=("alvo",))
    assert mantidos == {} and fora == {"alvo": 0.0}


# ---------- formatar ----------


def test_formatar_mostra_decisao_motivo_e_nd_para_metricas_ausentes() -> None:
    ok = Resultado(3, 480, 20.0, rmse_cm=4.0, rmse_persistencia_cm=8.0, rmse_tendencia_cm=6.5)
    ok.publicar, ok.motivo = True, "Superou a persistência na validação."
    nao = Resultado(24, 100, 4.2, motivo="Poucos dados para validar (100 horas completas).")
    texto = formatar([ok, nao])
    linhas = texto.splitlines()
    assert any("PUBLICADO: Superou" in ln and "4.0" in ln and "6.5" in ln for ln in linhas)
    assert any("não publicado: Poucos dados" in ln and "n/d" in ln for ln in linhas)
    assert "RMSE em cm" in texto


# ---------- treinar() com series e banco ----------


class RelogioFixo(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001, ANN206
        return AGORA.astimezone(tz) if tz else AGORA


@pytest.fixture
def ambiente(s: Session, monkeypatch: pytest.MonkeyPatch):
    """Banco semeado, relogio fixo e series falsas. Devolve o que o treino pediu e gravou."""
    semear(s)
    s.commit()
    visto: dict = {"janelas": [], "colunas": [], "registrados": [], "pontos_pedidos": []}
    cadastro: dict = {"chuva": {}, "nivel": {}}

    def chuva_horaria(sessao, codigo, ini, fim):  # noqa: ANN001, ANN202
        visto["janelas"].append((ini, fim))
        visto["pontos_pedidos"].append(codigo)
        return cadastro["chuva"].get(
            codigo, pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
        )

    def nivel_horario(sessao, codigo, ini, fim):  # noqa: ANN001, ANN202
        return cadastro["nivel"].get(
            codigo, pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
        )

    def avaliar(X, y, h):  # noqa: ANN001, ANN202
        visto["colunas"].append(list(X.columns))
        return Resultado(h, len(X), 1.0, publicar=(h == 3), motivo="m")

    def registrar(sessao, est, r, treinado_em, pasta):  # noqa: ANN001, ANN202
        visto["registrados"].append((est.codigo, r.horizonte_h, treinado_em))

    monkeypatch.setattr(treinar, "datetime", RelogioFixo)
    monkeypatch.setattr(treinar, "chuva_horaria", chuva_horaria)
    monkeypatch.setattr(treinar, "nivel_horario", nivel_horario)
    monkeypatch.setattr(treinar, "avaliar_horizonte", avaliar)
    monkeypatch.setattr(treinar, "registrar", registrar)
    return visto, cadastro


def serie_cheia(n: int, valor: float = 1.0) -> pd.Series:
    return pd.Series(valor, horas(n))


def test_estacao_inexistente_levanta_treino_impossivel(ambiente) -> None:
    with pytest.raises(TreinoImpossivel, match="nao encontrada"):
        treinar.treinar("DCSC-99999", salvar=False)


def test_alvo_sem_nenhuma_leitura_de_nivel_levanta_treino_impossivel(ambiente) -> None:
    with pytest.raises(TreinoImpossivel, match="sem leituras de nivel para DCSC-00174"):
        treinar.treinar(REVOLVER, salvar=False)


def test_alvo_com_nivel_de_cobertura_baixa_ainda_treina_e_o_vizinho_ralo_sai(ambiente) -> None:
    visto, cadastro = ambiente
    n = 24 * 30
    cadastro["nivel"][REVOLVER] = serie_cheia(n).where(np.arange(n) % 10 == 0)  # ~10% de cobertura
    cadastro["nivel"][PG] = serie_cheia(n).where(np.arange(n) % 10 == 0)
    cadastro["chuva"][REVOLVER] = serie_cheia(n)
    resultados = treinar.treinar(REVOLVER, dias=30, salvar=False)
    assert len(resultados) == len(HORIZONTES_H)
    colunas = visto["colunas"][0]
    assert "nivel_m" in colunas  # o alvo e obrigatorio
    assert "nivel_getulio_m" not in colunas  # vizinho com 10% de cobertura foi deixado de fora


def test_pontos_de_chuva_sem_cobertura_nao_geram_colunas(ambiente) -> None:
    visto, cadastro = ambiente
    n = 24 * 30
    cadastro["nivel"][REVOLVER] = serie_cheia(n)
    cadastro["chuva"][PG] = serie_cheia(n)
    cadastro["chuva"]["DC-PEU-003"] = serie_cheia(n).where(np.arange(n) < 100)  # 14% de cobertura
    treinar.treinar(REVOLVER, dias=30, salvar=False)
    colunas = visto["colunas"][0]
    assert any(c.startswith("chuva_local_") for c in colunas)
    assert not any("serra_indios" in c for c in colunas)  # ralo demais
    assert not any("serra_vencida" in c for c in colunas)  # sem nenhuma leitura


def test_retreino_do_pg_so_pede_os_pontos_de_chuva_do_pg(ambiente) -> None:
    """Sem decisao, o retreino diario do rio dos Indios nao pode ganhar serras nem o Revolver."""
    visto, cadastro = ambiente
    n = 24 * 30
    cadastro["nivel"][PG] = serie_cheia(n)
    for cod in (*pontos_chuva(PG), *pontos_chuva(REVOLVER)):
        cadastro["chuva"][cod] = serie_cheia(n)  # todos com dado: nada sai por cobertura
    treinar.treinar(PG, dias=30, salvar=False)
    assert set(visto["pontos_pedidos"]) == set(pontos_chuva(PG))
    colunas = visto["colunas"][0]
    assert not any("serra" in c or "revolver" in c for c in colunas)
    assert any(c.startswith("chuva_vitor_") for c in colunas)


def test_treina_um_resultado_por_horizonte_e_salva_so_quando_pedido(ambiente) -> None:
    visto, cadastro = ambiente
    cadastro["nivel"][PG] = serie_cheia(24 * 30)
    resultados = treinar.treinar(PG, dias=30, salvar=False)
    assert [r.horizonte_h for r in resultados] == list(HORIZONTES_H)
    assert visto["registrados"] == []
    treinar.treinar(PG, dias=30, salvar=True)
    assert [(c, h) for c, h, _ in visto["registrados"]] == [(PG, h) for h in HORIZONTES_H]
    assert {t for _, _, t in visto["registrados"]} == {AGORA}


def test_janela_e_hora_cheia_e_vem_do_padrao_do_alvo(ambiente) -> None:
    visto, cadastro = ambiente
    cadastro["nivel"][PG] = serie_cheia(24 * 30)
    treinar.treinar(PG, salvar=False)  # padrao do rio dos Indios: 120 dias
    ini, fim = visto["janelas"][0]
    assert fim == FIM and ini == FIM - timedelta(days=120)
    assert {j for j in visto["janelas"]} == {(ini, fim)}  # todos os pontos usam a mesma janela
    assert len(visto["janelas"]) == len(pontos_chuva(PG))


def test_revolver_sem_argumentos_usa_todo_o_historico_do_painel(ambiente) -> None:
    visto, cadastro = ambiente
    cadastro["nivel"][REVOLVER] = serie_cheia(24 * 30)
    treinar.treinar(REVOLVER, salvar=False)
    assert visto["janelas"][0][0] == datetime(2025, 9, 13, tzinfo=UTC)


def test_aviso_de_cobertura_baixa_vai_para_o_log(ambiente, caplog) -> None:
    _, cadastro = ambiente
    n = 24 * 30
    cadastro["nivel"][PG] = serie_cheia(n)
    cadastro["chuva"]["DC-PEU-003"] = serie_cheia(n).where(np.arange(n) < 100)
    with caplog.at_level(logging.WARNING, logger="modelo.treinar"):
        treinar.treinar(PG, dias=30, salvar=False)
    assert "pontos fora do treino por cobertura baixa" in caplog.text


# ---------- agendador ----------


def test_erro_de_um_alvo_vai_para_o_log_com_o_codigo(monkeypatch, caplog) -> None:
    def falso(alvo, dias=None, salvar=True, desde=None):  # noqa: ANN001, ANN202
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(agendador, "treinar", falso)
    with caplog.at_level(logging.ERROR, logger="modelo.agendador"):
        assert agendador.rodar() == {PG: False, REVOLVER: False}
    assert caplog.text.count("falha no treino") == 2 and "banco caiu" in caplog.text


def test_interrupcao_do_operador_nao_e_engolida_pelo_isolamento(monkeypatch) -> None:
    def falso(alvo, dias=None, salvar=True, desde=None):  # noqa: ANN001, ANN202
        raise KeyboardInterrupt

    monkeypatch.setattr(agendador, "treinar", falso)
    with pytest.raises(KeyboardInterrupt):
        agendador.rodar()


def test_rodar_com_alvos_explicitos_treina_so_eles_e_na_ordem_pedida(monkeypatch) -> None:
    chamados: list[str] = []
    monkeypatch.setattr(
        agendador,
        "treinar",
        lambda alvo, dias=None, salvar=True, desde=None: chamados.append(alvo) or [],
    )
    assert agendador.rodar(alvos=(REVOLVER,)) == {REVOLVER: True}
    assert chamados == [REVOLVER]


def test_resultado_de_cada_horizonte_e_registrado_no_log_com_publicacao(
    monkeypatch, caplog
) -> None:
    rs = [Resultado(1, 100, 4.0, publicar=True, motivo="ok"), Resultado(3, 100, 4.0, motivo="x")]
    monkeypatch.setattr(agendador, "treinar", lambda alvo, dias=None, salvar=True, desde=None: rs)
    with caplog.at_level(logging.INFO, logger="modelo.agendador"):
        agendador.rodar(alvos=(PG,))
    assert caplog.text.count("treino concluido") == 2


def test_servico_agenda_o_treino_diario_as_7h_utc_sem_sobreposicao(monkeypatch) -> None:
    registrado: dict = {}

    class AgendadorFalso:
        def __init__(self, timezone: str) -> None:
            registrado["timezone"] = timezone

        def add_job(self, func, trigger, **kw) -> None:  # noqa: ANN001, ANN003
            registrado.update(func=func, trigger=trigger, **kw)

        def start(self) -> None:
            registrado["iniciado"] = True

    monkeypatch.setattr(agendador, "BlockingScheduler", AgendadorFalso)
    monkeypatch.setattr("sys.argv", ["agendador", "--dias", "30"])
    agendador.principal()
    assert registrado["timezone"] == "UTC" and registrado["trigger"] == "cron"
    assert (registrado["hour"], registrado["minute"]) == (7, 0)
    assert registrado["max_instances"] == 1 and registrado["coalesce"] is True
    assert registrado["kwargs"] == {"dias": 30, "desde": None}
    assert registrado["func"] is agendador.rodar and registrado["iniciado"] is True


def test_todos_os_alvos_cadastrados_sao_treinados_pelo_agendador(monkeypatch) -> None:
    chamados: list[str] = []
    monkeypatch.setattr(
        agendador,
        "treinar",
        lambda alvo, dias=None, salvar=True, desde=None: chamados.append(alvo) or [],
    )
    agendador.rodar()
    assert chamados == list(ALVOS)
