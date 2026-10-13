from fastapi.testclient import TestClient


def test_contorno_e_um_geojson_de_poligono(client: TestClient) -> None:
    corpo = client.get("/api/municipio").json()
    geometria = corpo["features"][0]["geometry"]
    assert geometria["type"] == "Polygon"
    assert len(geometria["coordinates"][0]) > 20
