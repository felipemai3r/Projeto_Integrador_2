"""Ponto em poligono: anel fechado, concavidade e o contorno real do municipio."""

import pytest

from common.geo import contorno, dentro_do_municipio, ponto_no_anel

# letra "L" (concava), em (lon, lat)
L = [(0.0, 0.0), (0.0, 3.0), (1.0, 3.0), (1.0, 1.0), (3.0, 1.0), (3.0, 0.0)]


def test_anel_fechado_repetindo_o_primeiro_ponto_da_o_mesmo_resultado() -> None:
    fechado = [*L, L[0]]
    for lat, lon in [(0.5, 0.5), (2.0, 0.5), (0.5, 2.0), (2.0, 2.0), (5.0, 5.0)]:
        assert ponto_no_anel(lat, lon, fechado) == ponto_no_anel(lat, lon, L)


@pytest.mark.parametrize(
    ("lat", "lon", "esperado"),
    [
        (2.0, 0.5, True),  # haste vertical do L
        (0.5, 2.0, True),  # haste horizontal
        (2.0, 2.0, False),  # vao interno da concavidade
        (3.5, 0.5, False),  # acima
        (0.5, 3.5, False),  # a direita
        (-0.5, 0.5, False),  # abaixo
    ],
)
def test_poligono_concavo(lat: float, lon: float, esperado: bool) -> None:
    assert ponto_no_anel(lat, lon, L) is esperado


def test_anel_vazio_ou_degenerado_nunca_contem_ponto() -> None:
    assert ponto_no_anel(0.0, 0.0, []) is False
    assert ponto_no_anel(0.0, 0.0, [(0.0, 0.0), (1.0, 1.0)]) is False


def test_lat_e_lon_nao_sao_trocados() -> None:
    # (lat, lon) de Presidente Getulio dentro; trocar os eixos cai no oceano/fora do estado
    assert dentro_do_municipio(-27.0455, -49.6243) is True
    assert dentro_do_municipio(-49.6243, -27.0455) is False


def test_contorno_do_ibge_e_um_anel_fechado_de_80_vertices_em_lon_lat() -> None:
    anel = contorno()
    assert len(anel) == 80 and anel[0] == anel[-1]
    assert all(-50.0 < lon < -49.0 and -27.5 < lat < -26.7 for lon, lat in anel)


def test_contorno_e_carregado_uma_unica_vez() -> None:
    assert contorno() is contorno()


@pytest.mark.parametrize("codigo", ["DCSC-00043", "DCSC-00174", "DC-PEU-002", "DC-PEU-003"])
def test_estacoes_do_municipio_estao_dentro_do_contorno(codigo: str) -> None:
    from common.seed import ESTACOES, ESTACOES_PDC

    _, _, _, lat, lon, _ = next(e for e in ESTACOES + ESTACOES_PDC if e[0] == codigo)
    assert dentro_do_municipio(lat, lon)


def test_pontos_de_outros_municipios_vizinhos_ficam_fora() -> None:
    assert not dentro_do_municipio(-26.9548, -49.6336)  # Jose Boiteux
    assert not dentro_do_municipio(-27.0570, -49.5200)  # Ibirama
