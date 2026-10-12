"""Adaptadores do Open-Meteo: previsao de chuva (forecast) e reanalise ERA5 (archive).

- Forecast: chuva horaria prevista por estacao, gravada em previsao_chuva (RF04).
- Archive: chuva horaria historica (ERA5, desde 1940), gravada como leitura chuva_h001_mm da fonte
  openmeteo_archive. ERA5 suaviza picos convectivos (LD04): serve de contexto e regime, nunca
  de verdade de campo.
"""

from datetime import UTC, date, datetime
from typing import Any

import httpx
from common.enums import Variavel
from common.schemas import LeituraBruta, PrevisaoChuvaBruta

from ingestor.erros import ContratoQuebrado, FonteIndisponivel

Ponto = tuple[str, float, float]  # codigo da estacao, latitude, longitude
MODELO_FORECAST = "openmeteo_best_match"


def _hora(texto: str) -> datetime:
    """Open-Meteo devolve '2026-10-12T00:00' sem fuso, na timezone pedida (UTC)."""
    return datetime.fromisoformat(texto).replace(tzinfo=UTC)


def normalizar_forecast(
    codigo: str, resposta: dict[str, Any], gerado_em: datetime
) -> list[PrevisaoChuvaBruta]:
    try:
        h = resposta["hourly"]
        tempos, chuva = h["time"], h["precipitation"]
    except (KeyError, TypeError) as e:
        raise ContratoQuebrado(f"forecast {codigo}: {e!r}") from e
    prob = h.get("precipitation_probability") or [None] * len(tempos)
    saida: list[PrevisaoChuvaBruta] = []
    for t, mm, p in zip(tempos, chuva, prob, strict=False):
        if mm is None:
            continue
        saida.append(
            PrevisaoChuvaBruta(
                estacao_codigo=codigo,
                gerado_em=gerado_em,
                valido_para=_hora(t),
                chuva_mm=float(mm),
                probabilidade=None if p is None else float(p),
                modelo_fonte=MODELO_FORECAST,
            )
        )
    return saida


def normalizar_archive(codigo: str, resposta: dict[str, Any]) -> list[LeituraBruta]:
    try:
        h = resposta["hourly"]
        tempos, chuva = h["time"], h["precipitation"]
    except (KeyError, TypeError) as e:
        raise ContratoQuebrado(f"archive {codigo}: {e!r}") from e
    return [
        LeituraBruta(
            estacao_codigo=codigo,
            variavel=Variavel.CHUVA_H001_MM,
            valor=float(mm),
            unidade="mm",
            medido_em=_hora(t),
        )
        for t, mm in zip(tempos, chuva, strict=False)
        if mm is not None
    ]


class OpenMeteo:
    def __init__(
        self, url_forecast: str, url_archive: str, cliente: httpx.Client | None = None
    ) -> None:
        self._forecast = url_forecast
        self._archive = url_archive
        self._cliente = cliente or httpx.Client(timeout=60)

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self._cliente.get(url, params=params)
            r.raise_for_status()
            corpo: dict[str, Any] = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise FonteIndisponivel(f"open-meteo: {e!r}") from e
        return corpo

    def previsao(self, pontos: list[Ponto], dias: int = 3) -> list[PrevisaoChuvaBruta]:
        gerado_em = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        saida: list[PrevisaoChuvaBruta] = []
        for codigo, lat, lon in pontos:
            try:
                resp = self._get(
                    self._forecast,
                    {
                        "latitude": lat,
                        "longitude": lon,
                        "forecast_days": dias,
                        "timezone": "UTC",
                        "hourly": "precipitation,precipitation_probability",
                    },
                )
            except FonteIndisponivel:
                continue  # um ponto fora nao derruba os demais (RNF05)
            saida += normalizar_forecast(codigo, resp, gerado_em)
        return saida

    def historico(self, pontos: list[Ponto], inicio: date, fim: date) -> list[LeituraBruta]:
        saida: list[LeituraBruta] = []
        for codigo, lat, lon in pontos:
            resp = self._get(
                self._archive,
                {
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": inicio.isoformat(),
                    "end_date": fim.isoformat(),
                    "hourly": "precipitation",
                    "timezone": "UTC",
                },
            )
            saida += normalizar_archive(codigo, resp)
        return saida

    def verificar_contrato(self, ponto: Ponto) -> bool:
        try:
            resp = self._get(
                self._forecast,
                {
                    "latitude": ponto[1],
                    "longitude": ponto[2],
                    "forecast_days": 1,
                    "timezone": "UTC",
                    "hourly": "precipitation",
                },
            )
            return len(normalizar_forecast(ponto[0], resp, datetime.now(UTC))) > 0
        except (ContratoQuebrado, FonteIndisponivel):
            return False
