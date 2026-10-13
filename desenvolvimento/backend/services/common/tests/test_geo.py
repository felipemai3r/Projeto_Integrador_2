import pytest

from common.geo import dentro_do_municipio, ponto_no_anel


@pytest.mark.parametrize(
    ("lat", "lon", "esperado"),
    [
        (-27.0455, -49.6243, True),  # sede
        (-27.0551, -49.6155, True),  # Revolver
        (-26.9548, -49.6336, False),  # Jose Boiteux
        (-27.0570, -49.5200, False),  # Ibirama
        (-27.5900, -48.5500, False),  # Florianopolis
        (0.0, 0.0, False),
    ],
)
def test_pontos_conhecidos(lat: float, lon: float, esperado: bool) -> None:
    assert dentro_do_municipio(lat, lon) is esperado


def test_ponto_em_poligono_simples() -> None:
    quadrado = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    assert ponto_no_anel(0.5, 0.5, quadrado)
    assert not ponto_no_anel(1.5, 0.5, quadrado)
    assert not ponto_no_anel(0.5, -0.1, quadrado)
