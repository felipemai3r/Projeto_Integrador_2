"""Registro de modelos: so um publicado por estacao e horizonte, e o artefato em disco."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from common.models import Estacao
from common.seed import semear
from sqlalchemy import select
from sqlalchemy.orm import Session

from modelo.registry import carregar_artefato, publicados, registrar, ultimos_treinos
from modelo.treino import Resultado

T0 = datetime(2026, 11, 5, 7, 0, tzinfo=UTC)


class Pipe:
    """Objeto simples que o joblib consegue gravar."""

    def predict(self, X):  # noqa: ANN001, ANN201
        return [0.0]


@pytest.fixture
def estacoes(s: Session) -> tuple[Estacao, Estacao]:
    semear(s)
    s.commit()
    pg = s.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00043")).one()
    rev = s.scalars(select(Estacao).where(Estacao.codigo == "DCSC-00174")).one()
    return pg, rev


def resultado(h: int = 3, publicar: bool = True, pipeline: object | None = None) -> Resultado:
    return Resultado(
        horizonte_h=h,
        amostras=500,
        dias_uteis=20.8,
        rmse_cm=4.0,
        mae_cm=3.0,
        rmse_persistencia_cm=8.0,
        rmse_tendencia_cm=6.0,
        desvio_residual_cm=3.5,
        publicar=publicar,
        motivo="Superou a persistência na validação." if publicar else "Poucos dados.",
        colunas=["a", "b"],
        pipeline=Pipe() if pipeline is None and publicar else pipeline,
        faixa_treino={"a": (0.0, 1.0), "b": (-1.0, 1.0)},
        intervalo_por_regime={
            "seco": [-9.0, 9.5],
            "chuva": [-40.0, 55.0],
            "chuva_forte": [-70.0, 80.0],
        },
        alfa_intervalo=0.015,
        cobertura_validacao=0.957,
        colunas_obrigatorias=["a"],
    )


def test_modelo_publicado_grava_artefato_legivel_e_caminho_por_estacao_e_horizonte(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    m = registrar(s, pg, resultado(6), T0, str(tmp_path))
    s.commit()
    assert m.publicado is True
    assert Path(m.caminho_artefato) == tmp_path / "DCSC-00043" / "6" / f"{m.id}.joblib"
    art = carregar_artefato(m.caminho_artefato)
    assert art["colunas"] == ["a", "b"] and art["faixa_treino"]["a"] == (0.0, 1.0)
    assert isinstance(art["pipeline"], Pipe)
    # campos do modelo novo: a API usa para aceitar NaN e para o intervalo por regime
    assert art["aceita_nan"] is True and art["colunas_obrigatorias"] == ["a"]
    assert art["intervalo_por_regime"]["chuva"] == [-40.0, 55.0] and art["alfa_intervalo"] == 0.015


def test_metadados_guardam_motivo_colunas_e_erros_para_explicar_a_previsao(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    m = registrar(s, pg, resultado(3), T0, str(tmp_path))
    s.commit()
    s.refresh(m)
    assert m.metadados == {
        "motivo": "Superou a persistência na validação.",
        "dias_uteis": 20.8,
        "colunas": ["a", "b"],
        "rmse_tendencia_cm": 6.0,
        "desvio_residual_cm": 3.5,
        "intervalo_por_regime": {
            "seco": [-9.0, 9.5],
            "chuva": [-40.0, 55.0],
            "chuva_forte": [-70.0, 80.0],
        },
        "alfa_intervalo": 0.015,
        "cobertura_validacao": 0.957,
        "confianca_intervalo": 0.95,
        "colunas_obrigatorias": ["a"],
        "aceita_nan": True,
    }
    assert (m.algoritmo, m.amostras, m.treinado_em) == ("hist_gradient_boosting", 500, T0)
    assert (m.rmse_cm, m.mae_cm, m.rmse_persistencia_cm) == (4.0, 3.0, 8.0)


def test_nao_publicado_guarda_a_linha_com_o_motivo_mas_nenhum_arquivo(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    m = registrar(s, pg, resultado(3, publicar=False), T0, str(tmp_path))
    s.commit()
    assert m.publicado is False and m.caminho_artefato == ""
    assert m.metadados["motivo"] == "Poucos dados."
    assert list(tmp_path.iterdir()) == []


def test_resultado_publicavel_sem_pipeline_nao_vira_publicado(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    r = resultado(3)
    r.pipeline = None
    m = registrar(s, pg, r, T0, str(tmp_path))
    assert m.publicado is False and m.caminho_artefato == ""


def test_metricas_ausentes_viram_zero_e_nao_quebram(s: Session, estacoes, tmp_path: Path) -> None:
    pg, _ = estacoes
    r = Resultado(horizonte_h=1, amostras=10, dias_uteis=0.4, motivo="Poucos dados.")
    m = registrar(s, pg, r, T0, str(tmp_path))
    s.commit()
    assert (m.rmse_cm, m.mae_cm, m.rmse_persistencia_cm) == (0.0, 0.0, 0.0)


def test_novo_publicado_despublica_o_anterior_do_mesmo_horizonte_e_estacao(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    velho = registrar(s, pg, resultado(3), T0, str(tmp_path))
    s.commit()
    novo = registrar(s, pg, resultado(3), T0 + timedelta(days=1), str(tmp_path))
    s.commit()
    s.refresh(velho)
    assert (velho.publicado, novo.publicado) == (False, True)
    assert publicados(s, pg.id)[3].id == novo.id


def test_publicar_um_horizonte_ou_estacao_nao_mexe_nos_outros(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, rev = estacoes
    h6 = registrar(s, pg, resultado(6), T0, str(tmp_path))
    do_rev = registrar(s, rev, resultado(3), T0, str(tmp_path))
    s.commit()
    registrar(s, pg, resultado(3), T0 + timedelta(days=1), str(tmp_path))
    s.commit()
    s.refresh(h6)
    s.refresh(do_rev)
    assert h6.publicado is True and do_rev.publicado is True


def test_treino_nao_publicado_revoga_nada_e_mantem_o_modelo_vigente(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    vigente = registrar(s, pg, resultado(3), T0, str(tmp_path))
    s.commit()
    registrar(s, pg, resultado(3, publicar=False), T0 + timedelta(days=1), str(tmp_path))
    s.commit()
    s.refresh(vigente)
    assert vigente.publicado is True
    assert publicados(s, pg.id)[3].id == vigente.id


def test_publicados_so_traz_os_publicados_indexados_por_horizonte(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, rev = estacoes
    registrar(s, pg, resultado(1), T0, str(tmp_path))
    registrar(s, pg, resultado(12), T0, str(tmp_path))
    registrar(s, pg, resultado(24, publicar=False), T0, str(tmp_path))
    registrar(s, rev, resultado(3), T0, str(tmp_path))
    s.commit()
    assert sorted(publicados(s, pg.id)) == [1, 12]
    assert sorted(publicados(s, rev.id)) == [3]


def test_ultimos_treinos_traz_o_mais_recente_por_horizonte_publicado_ou_nao(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    registrar(s, pg, resultado(3), T0, str(tmp_path))
    recente = registrar(s, pg, resultado(3, publicar=False), T0 + timedelta(days=2), str(tmp_path))
    registrar(s, pg, resultado(3), T0 + timedelta(days=1), str(tmp_path))
    s.commit()
    ult = ultimos_treinos(s, pg.id)
    assert ult[3].id == recente.id and ult[3].publicado is False
    assert set(ult) == {3}


def test_ultimos_treinos_desempata_pelo_id_quando_o_horario_e_igual(
    s: Session, estacoes, tmp_path: Path
) -> None:
    pg, _ = estacoes
    registrar(s, pg, resultado(3, publicar=False), T0, str(tmp_path))
    ultimo = registrar(s, pg, resultado(3, publicar=False), T0, str(tmp_path))
    s.commit()
    assert ultimos_treinos(s, pg.id)[3].id == ultimo.id


def test_estacao_sem_treino_nao_tem_publicados_nem_ultimos(s: Session, estacoes) -> None:
    _, rev = estacoes
    assert publicados(s, rev.id) == {} and ultimos_treinos(s, rev.id) == {}
