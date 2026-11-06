"""Previsao: motivo de indisponibilidade, idade da linha, incerteza e aviso de chuva estimada."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest
from common.models import Estacao, Modelo
from common.seed import semear
from modelo.features import PONTOS_CHUVA, montar_features, pontos_chuva
from sklearn.dummy import DummyRegressor
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import previsao
from api.previsao import (
    HISTORICO_H,
    IDADE_MAXIMA_H,
    Quadros,
    _chuva_estimada,
    _motivo_indisponivel,
    escolher_linha,
    montar_quadros,
    prever,
)

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
PG = "DCSC-00043"
REVOLVER = "DCSC-00174"


# ---------- _motivo_indisponivel ----------


def treino(motivo: str | None, meta_none: bool = False) -> SimpleNamespace:
    return SimpleNamespace(metadados=None if meta_none else {"motivo": motivo})


def test_sem_treino_nenhum_diz_que_o_modelo_ainda_nao_foi_treinado() -> None:
    msg = _motivo_indisponivel(None)
    assert msg.startswith("O modelo ainda não foi treinado")
    assert "mais dados" in msg


def test_motivo_do_ultimo_treino_vai_depois_da_frase_padrao() -> None:
    msg = _motivo_indisponivel(treino("Só há 20 dias de dados completos."))
    assert msg == "A previsão ainda não está disponível. Só há 20 dias de dados completos."


def test_treino_antigo_com_ponto_decimal_e_reescrito_com_virgula_e_duas_casas() -> None:
    msg = _motivo_indisponivel(treino("erro de 45.2 cm contra 30 cm de quem repete o nível"))
    assert "45,20 cm contra 30,00 cm" in msg


def test_numero_ja_em_formato_brasileiro_nao_e_alterado_duas_vezes() -> None:
    """O treino atual grava o motivo com cm_br (virgula). Esperado: '45,20 cm' inalterado."""
    msg = _motivo_indisponivel(treino("erro de 45,20 cm contra 30,00 cm"))
    assert msg.endswith("erro de 45,20 cm contra 30,00 cm")


def test_so_o_numero_que_precede_cm_e_reformatado() -> None:
    msg = _motivo_indisponivel(treino("Só há 12 dias; erro de 7.5 cm"))
    assert "Só há 12 dias" in msg and "7,50 cm" in msg


def test_metadados_ausentes_ou_sem_motivo_nao_quebram_nem_deixam_espaco_sobrando() -> None:
    assert (
        _motivo_indisponivel(treino(None, meta_none=True))
        == "A previsão ainda não está disponível."
    )
    assert (
        _motivo_indisponivel(SimpleNamespace(metadados={}))
        == "A previsão ainda não está disponível."
    )


# ---------- escolher_linha ----------


def serie_horaria(n: int, fim: pd.Timestamp, valor: float = 1.0) -> pd.Series:
    return pd.Series(valor, pd.date_range(end=fim, periods=n, freq="1h", tz="UTC"))


def mundo(fim: pd.Timestamp, n: int = HISTORICO_H) -> tuple[dict, dict]:
    chuva = {c: serie_horaria(n, fim) for c in PONTOS_CHUVA}
    nivel = {
        PG: serie_horaria(n, fim, 2.0) + np.linspace(0, 0.5, n),
        "DCSC-00021": serie_horaria(n, fim, 2.2),
        "DCSC-00020": serie_horaria(n, fim, 1.9),
    }
    return chuva, nivel


FIM = pd.Timestamp(AGORA)


def quadros(chuva: dict, nivel: dict, alvo: str = PG, estimada: dict | None = None, horas=None):
    """Quadros como `montar_quadros` os monta, a partir de series ja prontas."""
    return Quadros(
        medido=montar_features(chuva, nivel, alvo=alvo),
        estimado=montar_features(estimada, nivel, alvo=alvo) if estimada is not None else None,
        horas_estimadas=horas or {},
    )


def todas(q: Quadros) -> list[str]:
    return list(q.medido.columns)


def sem_serras(q: Quadros) -> list[str]:
    return [c for c in todas(q) if "serra" not in c]


def test_linha_mais_recente_completa_e_devolvida_com_seu_horario() -> None:
    chuva, nivel = mundo(FIM)
    q = quadros(chuva, nivel)
    linha, t, estimadas = escolher_linha(q, todas(q), AGORA)
    assert t == FIM and linha["nivel_m"] == pytest.approx(2.5) and estimadas == {}


def test_linha_com_exatamente_3_horas_de_idade_ainda_serve_e_com_um_segundo_a_mais_nao() -> None:
    chuva, nivel = mundo(FIM)
    q = quadros(chuva, nivel)
    assert IDADE_MAXIMA_H == 3
    assert escolher_linha(q, todas(q), AGORA + timedelta(hours=3)) is not None
    assert escolher_linha(q, todas(q), AGORA + timedelta(hours=3, seconds=1)) is None


def test_historico_curto_demais_para_a_janela_de_168h_nao_gera_linha() -> None:
    chuva, nivel = mundo(FIM, n=100)  # as janelas de 72 h e 168 h nunca fecham
    q = quadros(chuva, nivel)
    assert escolher_linha(q, todas(q), AGORA) is None


def test_coluna_que_o_modelo_nao_tem_no_quadro_nao_gera_linha() -> None:
    chuva, nivel = mundo(FIM)
    assert escolher_linha(quadros(chuva, nivel), ["coluna_inexistente"], AGORA) is None


def test_so_as_colunas_do_modelo_contam_serra_fora_do_ar_nao_afeta_quem_nao_a_usa() -> None:
    chuva, nivel = mundo(FIM)
    nivel[REVOLVER] = serie_horaria(HISTORICO_H, FIM, 1.0)
    nivel[PG] = nivel[PG].copy()
    chuva["DC-PEU-004"] = chuva["DC-PEU-004"].copy()
    chuva["DC-PEU-004"].iloc[-6:] = np.nan  # serra fora do ar ha 6 h
    q = quadros(chuva, nivel, REVOLVER)
    # modelo que usa a serra: a ultima hora completa tem 6 h (alem do limite de idade)
    assert escolher_linha(q, todas(q), AGORA) is None
    # modelo que nao a usa: a hora mais recente, mesmo com a serra NaN na linha
    linha, t, _ = escolher_linha(q, sem_serras(q), AGORA)
    assert t == FIM and np.isnan(linha["chuva_serra_vencida_1h"])
    assert not np.isnan(linha["chuva_local_1h"]) and not np.isnan(linha["nivel_m"])


def test_falta_em_coluna_do_modelo_derruba_so_quem_a_usa() -> None:
    chuva, nivel = mundo(FIM)
    chuva["DCSC-00037"] = chuva["DCSC-00037"].copy()
    chuva["DCSC-00037"].iloc[-6:] = np.nan  # Dona Emma fora do ar
    q = quadros(chuva, nivel)
    assert escolher_linha(q, todas(q), AGORA) is None  # usa a Emma
    sem_emma = [c for c in todas(q) if "emma" not in c]
    assert escolher_linha(q, sem_emma, AGORA)[1] == FIM  # nao usa


def test_falta_de_nivel_do_alvo_derruba_qualquer_modelo() -> None:
    chuva, nivel = mundo(FIM)
    nivel[PG] = nivel[PG].copy()
    nivel[PG].iloc[-6:] = np.nan
    q = quadros(chuva, nivel)
    assert escolher_linha(q, ["chuva_local_1h"], AGORA) is None  # nivel_m e sempre exigido


def test_cada_modelo_pega_a_linha_mais_recente_que_o_serve() -> None:
    chuva, nivel = mundo(FIM)
    nivel[REVOLVER] = serie_horaria(HISTORICO_H, FIM, 1.0)
    chuva["DC-PEU-004"] = chuva["DC-PEU-004"].copy()
    chuva["DC-PEU-004"].iloc[-2:] = np.nan  # serra sem as 2 ultimas horas
    q = quadros(chuva, nivel, REVOLVER)
    assert escolher_linha(q, sem_serras(q), AGORA)[1] == FIM
    assert escolher_linha(q, todas(q), AGORA)[1] == FIM - pd.Timedelta(hours=2)


def test_pluviometro_do_proprio_revolver_fora_do_ar_so_afeta_quem_o_usa() -> None:
    chuva, nivel = mundo(FIM)
    nivel[REVOLVER] = serie_horaria(HISTORICO_H, FIM, 1.0)
    chuva[REVOLVER] = chuva[REVOLVER].copy()
    chuva[REVOLVER].iloc[-6:] = np.nan
    q = quadros(chuva, nivel, REVOLVER)
    sem_pluv = [c for c in todas(q) if "revolver" not in c]
    linha, t, _ = escolher_linha(q, sem_pluv, AGORA)
    assert t == FIM and np.isnan(linha["chuva_revolver_1h"])
    assert escolher_linha(q, todas(q), AGORA) is None


def test_mesma_hora_prefere_a_chuva_medida_a_estimada() -> None:
    chuva, nivel = mundo(FIM)
    estimada = {c: v + 100.0 for c, v in chuva.items()}  # valores distintos para distinguir
    q = quadros(chuva, nivel, estimada=estimada, horas={"DCSC-00036": pd.DatetimeIndex([FIM])})
    linha, t, est = escolher_linha(q, todas(q), AGORA)
    assert t == FIM and linha["chuva_local_1h"] == pytest.approx(1.0) and est == {}


def test_hora_estimada_mais_recente_vence_a_medida_mais_antiga() -> None:
    chuva, nivel = mundo(FIM)
    chuva["DCSC-00036"] = chuva["DCSC-00036"].copy()
    chuva["DCSC-00036"].iloc[-2:] = np.nan  # Vitor sem as 2 ultimas horas
    estimada = {c: v.copy() for c, v in chuva.items()}
    estimada["DCSC-00036"] = estimada["DCSC-00036"].fillna(1.0)
    horas = {"DCSC-00036": pd.date_range(end=FIM, periods=2, freq="1h")}
    q = quadros(chuva, nivel, estimada=estimada, horas=horas)
    _, t, est = escolher_linha(q, todas(q), AGORA)
    assert t == FIM and est == {"DCSC-00036": 2}
    # um modelo que nao usa a Vitor nao recebe aviso de estimativa
    sem_vitor = [c for c in todas(q) if "vitor" not in c]
    _, t_sem, est_sem = escolher_linha(q, sem_vitor, AGORA)
    assert t_sem == FIM and est_sem == {}


def test_montar_quadros_sem_nivel_do_alvo_devolve_none(monkeypatch: pytest.MonkeyPatch) -> None:
    vazia = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    monkeypatch.setattr(previsao, "chuva_horaria", lambda s, c, ini, fim: vazia)
    monkeypatch.setattr(previsao, "nivel_horario", lambda s, c, ini, fim: vazia)
    assert montar_quadros(None, PG, AGORA) is None  # type: ignore[arg-type]


def test_montar_quadros_so_pede_os_pontos_do_alvo(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos: list[str] = []

    def chuva(s, c, ini, fim):  # noqa: ANN001, ANN202
        pedidos.append(c)
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))

    monkeypatch.setattr(previsao, "chuva_horaria", chuva)
    monkeypatch.setattr(
        previsao, "nivel_horario", lambda s, c, ini, fim: serie_horaria(HISTORICO_H, FIM)
    )
    montar_quadros(None, PG, AGORA)  # type: ignore[arg-type]
    assert set(pedidos) == set(pontos_chuva(PG))
    pedidos.clear()
    montar_quadros(None, REVOLVER, AGORA)  # type: ignore[arg-type]
    assert set(pedidos) == set(pontos_chuva(REVOLVER))


# ---------- _chuva_estimada ----------


def test_chuva_estimada_traz_nome_da_estacao_e_ordena_por_codigo(s: Session) -> None:
    semear(s)
    s.commit()
    r = _chuva_estimada(s, {"DC-PEU-004": 2, "DCSC-00036": 14})
    assert [(x.codigo, x.nome, x.horas) for x in r] == [
        ("DC-PEU-004", "PCD Serra Vencida (Escola Serra Vencida)", 2),
        ("DCSC-00036", "PCD Vitor Meireles", 14),
    ]


def test_chuva_estimada_vazia_nao_consulta_o_banco() -> None:
    assert _chuva_estimada(None, {}) == []  # type: ignore[arg-type]


def test_ponto_desconhecido_no_banco_usa_o_codigo_como_nome(s: Session) -> None:
    semear(s)
    s.commit()
    assert _chuva_estimada(s, {"XYZ": 3})[0].nome == "XYZ"


# ---------- prever ----------


@pytest.fixture
def base(s: Session) -> Session:
    semear(s)
    s.commit()
    return s


def estacao(s: Session, codigo: str) -> Estacao:
    return s.scalars(select(Estacao).where(Estacao.codigo == codigo)).one()


def publica(
    s: Session,
    tmp: Path,
    codigo: str,
    h: int,
    delta_cm: float,
    meta: dict | None = None,
    rmse: float = 5.0,
    colunas: tuple[str, ...] = ("nivel_m",),
) -> Modelo:
    pipe = DummyRegressor(strategy="constant", constant=delta_cm)
    pipe.fit(pd.DataFrame({c: [1.0, 2.0] for c in colunas}), [delta_cm, delta_cm])
    caminho = tmp / f"{codigo}_{h}.joblib"
    joblib.dump({"pipeline": pipe, "colunas": list(colunas), "faixa_treino": {}}, caminho)
    m = Modelo(
        estacao_id=estacao(s, codigo).id,
        horizonte_h=h,
        algoritmo="ridge",
        treinado_em=AGORA,
        amostras=500,
        rmse_cm=rmse,
        mae_cm=1.0,
        rmse_persistencia_cm=10.0,
        publicado=True,
        caminho_artefato=str(caminho),
        metadados=meta if meta is not None else {},
    )
    s.add(m)
    s.commit()
    return m


def com_linha(monkeypatch: pytest.MonkeyPatch, nivel: float, extras: dict | None = None) -> None:
    """Fixa as variaveis "de agora": uma unica hora (1 h atras) so com o nivel (e `extras`)."""
    t = pd.Timestamp(AGORA - timedelta(hours=1))
    quadro = pd.DataFrame({"nivel_m": [nivel], **{c: [v] for c, v in (extras or {}).items()}}, [t])
    achados = Quadros(medido=quadro, estimado=None, horas_estimadas={})
    monkeypatch.setattr(previsao, "montar_quadros", lambda s, estacao, agora: achados)


def horizonte(r, h: int):
    return next(x for x in r.horizontes if x.horizonte_h == h)


def test_nivel_previsto_e_o_atual_mais_a_variacao_do_modelo(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, REVOLVER, 3, delta_cm=40.0)
    com_linha(monkeypatch, 2.50)
    r = prever(base, estacao(base, REVOLVER), AGORA)
    h3 = horizonte(r, 3)
    assert h3.disponivel and h3.nivel_m == 2.90
    assert h3.valido_para == AGORA - timedelta(hours=1) + timedelta(hours=3)
    assert (r.nivel_base_m, r.base_em, r.origem) == (2.5, AGORA - timedelta(hours=1), "operacional")


def test_faixa_prevista_usa_os_limiares_do_alvo(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, REVOLVER, 3, delta_cm=60.0)
    com_linha(monkeypatch, 2.50)  # 3,10 m: alerta no Revolver (3,0) e normal no rio dos Indios
    assert horizonte(prever(base, estacao(base, REVOLVER), AGORA), 3).faixa == "alerta"


def test_estacao_sem_limiares_tem_previsao_mas_nao_tem_faixa(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, "DCSC-00021", 3, delta_cm=10.0)
    com_linha(monkeypatch, 5.0)
    h3 = horizonte(prever(base, estacao(base, "DCSC-00021"), AGORA), 3)
    assert h3.disponivel and h3.faixa is None


def test_incerteza_usa_o_desvio_residual_e_o_intervalo_e_simetrico(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, REVOLVER, 3, 0.0, meta={"desvio_residual_cm": 10.0}, rmse=99.0)
    com_linha(monkeypatch, 2.0)
    h3 = horizonte(prever(base, estacao(base, REVOLVER), AGORA), 3)
    assert h3.incerteza_m == 0.2  # 1,96 * 10 cm = 19,6 cm
    assert h3.intervalo_m == (1.8, 2.2)


def test_sem_desvio_residual_cai_no_rmse_do_modelo(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, REVOLVER, 3, 0.0, meta={}, rmse=25.0)
    com_linha(monkeypatch, 2.0)
    h3 = horizonte(prever(base, estacao(base, REVOLVER), AGORA), 3)
    assert h3.incerteza_m == 0.49  # 1,96 * 25 cm


def test_horizonte_sem_modelo_explica_o_motivo_do_ultimo_treino(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, REVOLVER, 3, 10.0)
    base.add(
        Modelo(
            estacao_id=estacao(base, REVOLVER).id,
            horizonte_h=6,
            algoritmo="ridge",
            treinado_em=AGORA,
            amostras=10,
            rmse_cm=0.0,
            mae_cm=0.0,
            rmse_persistencia_cm=0.0,
            publicado=False,
            caminho_artefato="",
            metadados={"motivo": "Só há 12 dias de dados completos."},
        )
    )
    base.commit()
    com_linha(monkeypatch, 2.0)
    r = prever(base, estacao(base, REVOLVER), AGORA)
    h6, h24 = horizonte(r, 6), horizonte(r, 24)
    assert not h6.disponivel and "Só há 12 dias" in h6.motivo
    assert not h24.disponivel and "ainda não foi treinado" in h24.motivo
    assert h6.nivel_m is None and h24.intervalo_m is None


def test_aviso_de_chuva_estimada_so_aparece_quando_alguma_estimativa_sai(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = pd.Timestamp(AGORA - timedelta(hours=1))
    quadros_ = Quadros(  # a chuva da Vitor so existe estimada (5 h entraram na janela)
        medido=pd.DataFrame({"nivel_m": [2.0], "chuva_vitor_1h": [np.nan]}, [t]),
        estimado=pd.DataFrame({"nivel_m": [2.0], "chuva_vitor_1h": [1.0]}, [t]),
        horas_estimadas={"DCSC-00036": pd.date_range(end=t, periods=5, freq="1h")},
    )
    monkeypatch.setattr(previsao, "montar_quadros", lambda s, estacao, agora: quadros_)
    sem_modelo = prever(base, estacao(base, REVOLVER), AGORA)
    assert sem_modelo.chuva_estimada == []  # nenhum horizonte usou a chuva
    publica(base, tmp_path, REVOLVER, 3, 10.0)  # modelo que nao usa a Vitor
    assert prever(base, estacao(base, REVOLVER), AGORA).chuva_estimada == []
    publica(base, tmp_path, REVOLVER, 6, 10.0, colunas=("nivel_m", "chuva_vitor_1h"))
    com_modelo = prever(base, estacao(base, REVOLVER), AGORA)
    assert [(c.codigo, c.horas) for c in com_modelo.chuva_estimada] == [("DCSC-00036", 5)]
    assert horizonte(com_modelo, 6).disponivel and horizonte(com_modelo, 3).disponivel


def test_sem_linha_atual_todos_os_horizontes_publicados_dizem_sem_dados(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, REVOLVER, 3, 10.0)
    monkeypatch.setattr(previsao, "montar_quadros", lambda s, estacao, agora: None)
    r = prever(base, estacao(base, REVOLVER), AGORA)
    h3 = horizonte(r, 3)
    assert not h3.disponivel and "Sem dados recentes" in h3.motivo and h3.modelo is not None
    assert (r.base_em, r.nivel_base_m, r.chuva_estimada) == (None, None, [])


def test_cenario_marca_a_origem_e_nao_altera_a_previsao_de_quem_nao_usa_chuva(
    base: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publica(base, tmp_path, REVOLVER, 3, 10.0)
    com_linha(monkeypatch, 2.0)
    r = prever(base, estacao(base, REVOLVER), AGORA, chuva_mm={REVOLVER: 50.0})
    assert r.origem == "cenario" and horizonte(r, 3).nivel_m == 2.1
