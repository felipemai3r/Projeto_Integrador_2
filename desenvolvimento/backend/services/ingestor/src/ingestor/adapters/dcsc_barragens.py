"""Adaptador das barragens da Defesa Civil de SC (GET /api/barragens). Foco: Barragem Norte.

Escala: a rota devolve a COTA absoluta (ex.: 273,95 m acima do mar). A serie REST das estacoes
devolve a altura sobre o fundo (cota menos o nivel minimo, 256 m na Barragem Norte). Normalizamos
tudo para a altura sobre o fundo (reservatorio_m), para as duas fontes serem comparaveis
(confirmado em 12/10/2026: 273,95 - 256 = 17,95, mesmo valor da serie REST no mesmo instante).
"""

from datetime import datetime
from typing import Any

import httpx
from common.enums import Variavel
from common.schemas import LeituraBruta

from ingestor.adapters.base import Adaptador
from ingestor.erros import ContratoQuebrado, FonteIndisponivel

ESTACAO_BARRAGEM_NORTE = "DCSC-00042"
COMPORTAS = {
    "galeria": Variavel.COMPORTA_GALERIA,
    "tulipa258": Variavel.COMPORTA_TULIPA258,
    "tulipa264": Variavel.COMPORTA_TULIPA264,
}


def normalizar(resposta: dict[str, Any]) -> list[LeituraBruta]:
    """Converte a resposta de /api/barragens (barragemNorte) em leituras internas."""
    try:
        norte = resposta["data"]["barragemNorte"]
        minimo = float(norte["limites"]["minimo"])
        historico = norte["historico"]
        ultima = datetime.fromisoformat(norte["ultimaLeitura"])
    except (KeyError, TypeError, ValueError) as e:
        raise ContratoQuebrado(f"barragemNorte fora do formato esperado: {e!r}") from e

    leituras: list[LeituraBruta] = []
    for ponto in historico:
        try:
            medido_em = datetime.fromisoformat(ponto["timestamp"])
            cota = float(ponto["nivel"])
        except (KeyError, TypeError, ValueError) as e:
            raise ContratoQuebrado(f"ponto de historico invalido: {ponto!r}") from e
        leituras.append(
            LeituraBruta(
                estacao_codigo=ESTACAO_BARRAGEM_NORTE,
                variavel=Variavel.RESERVATORIO_M,
                valor=round(cota - minimo, 3),
                unidade="m",
                medido_em=medido_em,
                bruto=ponto,
            )
        )
        pct = ponto.get("nivel_porc")
        if isinstance(pct, int | float):
            leituras.append(
                LeituraBruta(
                    estacao_codigo=ESTACAO_BARRAGEM_NORTE,
                    variavel=Variavel.RESERVATORIO_PCT,
                    valor=float(pct),
                    unidade="%",
                    medido_em=medido_em,
                    bruto=ponto,
                )
            )

    comportas = norte.get("comportas") or {}
    for chave, variavel in COMPORTAS.items():
        if isinstance(comportas.get(chave), bool):
            leituras.append(
                LeituraBruta(
                    estacao_codigo=ESTACAO_BARRAGEM_NORTE,
                    variavel=variavel,
                    valor=1.0 if comportas[chave] else 0.0,
                    unidade="aberta",
                    medido_em=ultima,
                    bruto={chave: comportas[chave]},
                )
            )
    return leituras


class DcscBarragens(Adaptador):
    codigo = "dcsc_barragens"
    frequencia_s = 1800

    def __init__(self, base_url: str, cliente: httpx.Client | None = None) -> None:
        self._url = base_url.rstrip("/") + "/api/barragens"
        self._cliente = cliente or httpx.Client(timeout=30)

    def _buscar(self) -> dict[str, Any]:
        try:
            r = self._cliente.get(self._url)
            r.raise_for_status()
            corpo: dict[str, Any] = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise FonteIndisponivel(f"{self.codigo}: {e!r}") from e
        return corpo

    def coletar(
        self, inicio: datetime | None = None, fim: datetime | None = None
    ) -> list[LeituraBruta]:
        return normalizar(self._buscar())

    def verificar_contrato(self) -> bool:
        try:
            return len(normalizar(self._buscar())) > 0
        except (ContratoQuebrado, FonteIndisponivel):
            return False
