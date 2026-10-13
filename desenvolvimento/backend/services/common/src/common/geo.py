"""Geografia do municipio. Sem PostGIS: ponto-em-poligono feito na aplicacao.

O contorno vem da malha do IBGE (codigo 4214003, qualidade intermediaria, 80 vertices, conferida
em 13/10/2026). Serve para recusar registros fora de Presidente Getulio, nao para delimitar
propriedade: a precisao e da ordem de dezenas de metros.
"""

import json
from functools import lru_cache
from importlib import resources

Anel = list[tuple[float, float]]  # (longitude, latitude)


@lru_cache
def contorno() -> Anel:
    texto = (resources.files("common") / "data" / "presidente_getulio.geojson").read_text()
    anel = json.loads(texto)["features"][0]["geometry"]["coordinates"][0]
    return [(float(x), float(y)) for x, y in anel]


def ponto_no_anel(lat: float, lon: float, anel: Anel) -> bool:
    """Algoritmo do raio (par/impar de cruzamentos)."""
    dentro = False
    n = len(anel)
    for i in range(n):
        x1, y1 = anel[i]
        x2, y2 = anel[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            dentro = not dentro
    return dentro


def dentro_do_municipio(lat: float, lon: float) -> bool:
    return ponto_no_anel(lat, lon, contorno())
