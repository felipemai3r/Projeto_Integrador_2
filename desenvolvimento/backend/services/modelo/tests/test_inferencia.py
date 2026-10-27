import numpy as np
import pandas as pd
import pytest

from modelo.inferencia import imputar_chuva


def serie(valores: list[float], n: int | None = None) -> pd.Series:
    n = n or len(valores)
    idx = pd.date_range("2026-10-01", periods=n, freq="1h", tz="UTC")
    return pd.Series(valores, idx, dtype=float)


def pontos(n: int = 48) -> dict[str, pd.Series]:
    return {
        "A": serie([1.0] * n),
        "B": serie([2.0] * n),
        "C": serie([6.0] * n),
        "D": serie([0.0] * n),
    }


def test_preenche_com_a_media_dos_outros_pontos() -> None:
    p = pontos()
    p["D"].iloc[10:14] = np.nan
    novo, horas = imputar_chuva(p)
    assert novo["D"].iloc[10:14].tolist() == [3.0] * 4  # media de A, B e C
    assert novo["D"].iloc[:10].eq(0.0).all() and novo["D"].notna().all()
    assert list(horas["D"]) == list(p["D"].index[10:14])
    assert set(horas) == {"D"}


def test_exige_ao_menos_dois_vizinhos_com_dado_na_hora() -> None:
    p = {"A": serie([1.0] * 10), "B": serie([2.0] * 10), "C": serie([5.0] * 10)}
    p["A"].iloc[3] = np.nan
    p["B"].iloc[3] = np.nan  # so C tem dado nessa hora: nao basta para A nem para B
    p["C"].iloc[6] = np.nan  # A e B tem: ok
    novo, horas = imputar_chuva(p)
    assert np.isnan(novo["A"].iloc[3]) and np.isnan(novo["B"].iloc[3])
    assert novo["C"].iloc[6] == pytest.approx(1.5)
    assert "A" not in horas and list(horas["C"]) == [p["C"].index[6]]


def test_ponto_com_poucos_vizinhos_no_total_nao_e_tocado() -> None:
    p = {"A": serie([1.0, np.nan, 1.0]), "B": serie([2.0, 2.0, 2.0])}
    novo, horas = imputar_chuva(p)
    assert np.isnan(novo["A"].iloc[1]) and horas == {}


def test_respeita_o_limite_de_horas_do_ponto() -> None:
    p = pontos(100)
    p["D"].iloc[-25:] = np.nan
    novo, horas = imputar_chuva(p, max_horas=24)
    assert novo["D"].isna().sum() == 25 and "D" not in horas  # 25 > 24: nao mexe
    novo, horas = imputar_chuva(p, max_horas=25)
    assert novo["D"].notna().all() and len(horas["D"]) == 25


def test_so_olha_a_janela_final() -> None:
    p = pontos(300)
    p["D"].iloc[5:100] = np.nan  # lacuna antiga, fora das ultimas 168 h
    p["D"].iloc[-3:] = np.nan
    novo, horas = imputar_chuva(p, janela_h=168, max_horas=24)
    assert novo["D"].iloc[5:100].isna().all()  # antiga: continua NaN e nao conta no limite
    assert novo["D"].iloc[-3:].notna().all() and len(horas["D"]) == 3


def test_hora_final_ausente_de_um_ponto_conta_como_lacuna() -> None:
    p = pontos(48)
    p["D"] = p["D"].iloc[:-5]  # serie termina 5 h antes das demais
    novo, horas = imputar_chuva(p)
    assert len(novo["D"]) == 48 and novo["D"].iloc[-5:].eq(3.0).all()
    assert len(horas["D"]) == 5


def test_nao_altera_as_series_recebidas_e_devolve_as_intactas_iguais() -> None:
    p = pontos()
    p["D"].iloc[10:12] = np.nan
    copia = {c: v.copy() for c, v in p.items()}
    novo, _ = imputar_chuva(p)
    for c in p:
        pd.testing.assert_series_equal(p[c], copia[c])
    assert novo["A"] is p["A"]
    assert p["D"].isna().sum() == 2


def test_series_vazias_e_dicionario_vazio_sao_ignorados() -> None:
    vazia = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    assert imputar_chuva({}) == ({}, {})
    novo, horas = imputar_chuva({**pontos(), "E": vazia})
    assert novo["E"].empty and horas == {}
