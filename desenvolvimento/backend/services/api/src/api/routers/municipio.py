import json
from importlib import resources
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/municipio", tags=["geografia"])


@router.get("")
def contorno() -> dict[str, Any]:
    """Contorno de Presidente Getulio (GeoJSON, malha do IBGE) para desenhar no mapa."""
    texto = (resources.files("common") / "data" / "presidente_getulio.geojson").read_text()
    resultado: dict[str, Any] = json.loads(texto)
    return resultado
