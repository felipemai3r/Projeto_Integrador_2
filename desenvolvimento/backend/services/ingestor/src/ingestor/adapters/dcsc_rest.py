"""Adaptador da API REST anterior da Defesa Civil de SC.

Unica via anonima com serie de 5 em 5 minutos, com retencao de cerca de 80 dias
(docs/fontes-de-dados.md, secao 4). Serve a carga inicial e o preenchimento de lacunas.
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
from common.enums import Variavel
from common.schemas import LeituraBruta

from ingestor.adapters.base import Adaptador
from ingestor.erros import ContratoQuebrado, FonteIndisponivel

FUSO_SC = timezone(timedelta(hours=-3))

# Na barragem, "rio_nivel_m" e a cota absoluta do reservatorio (ex.: 273,95 m acima do mar),
# nao a altura de um rio. Guardar como nivel_m contaminaria a serie de nivel de rio.
ESTACOES_RESERVATORIO = {"DCSC-00042"}


def _formatar(dt: datetime) -> str:
    """Formato aceito pela fonte: 2026-09-18T00:00-0300."""
    return dt.astimezone(FUSO_SC).strftime("%Y-%m-%dT%H:%M%z")


def normalizar(codigo: str, resposta: dict[str, Any]) -> list[LeituraBruta]:
    """Converte a serie de uma estacao em leituras internas. Funcao pura."""
    dados = resposta.get("dados")
    if not isinstance(dados, list):
        raise ContratoQuebrado(f"{codigo}: resposta sem lista 'dados'")
    leituras: list[LeituraBruta] = []
    for ponto in dados:
        try:
            medido_em = datetime.fromisoformat(ponto["timestamp"])
        except (KeyError, TypeError, ValueError) as e:
            raise ContratoQuebrado(f"{codigo}: ponto sem timestamp valido: {ponto!r}") from e
        nivel = Variavel.RESERVATORIO_M if codigo in ESTACOES_RESERVATORIO else Variavel.NIVEL_M
        for campo, variavel, unidade in (
            ("rio_nivel_m", nivel, "m"),
            ("chuva_acumulada_mm", Variavel.CHUVA_ACUMULADA_MM, "mm"),
        ):
            valor = ponto.get(campo)
            if isinstance(valor, int | float):
                leituras.append(
                    LeituraBruta(
                        estacao_codigo=codigo,
                        variavel=variavel,
                        valor=float(valor),
                        unidade=unidade,
                        medido_em=medido_em,
                        bruto=ponto,
                    )
                )
    return leituras


class DcscRest(Adaptador):
    codigo = "dcsc_rest"
    frequencia_s = 1800

    def __init__(
        self, base_url: str, estacoes: list[str], cliente: httpx.Client | None = None
    ) -> None:
        self._base = base_url.rstrip("/")
        self._estacoes = estacoes
        self._cliente = cliente or httpx.Client(timeout=30)

    def coletar_estacao(self, codigo: str, inicio: datetime, fim: datetime) -> list[LeituraBruta]:
        try:
            r = self._cliente.get(
                f"{self._base}/api/estacoes/dados",
                params={
                    "codigo": codigo,
                    "data_inicial": _formatar(inicio),
                    "data_final": _formatar(fim),
                },
            )
            r.raise_for_status()
            corpo: dict[str, Any] = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise FonteIndisponivel(f"{self.codigo} {codigo}: {e!r}") from e
        return normalizar(codigo, corpo)

    def coletar(
        self, inicio: datetime | None = None, fim: datetime | None = None
    ) -> list[LeituraBruta]:
        fim = fim or datetime.now(UTC)
        inicio = inicio or fim - timedelta(hours=2)
        resultado: list[LeituraBruta] = []
        for codigo in self._estacoes:
            try:
                resultado += self.coletar_estacao(codigo, inicio, fim)
            except FonteIndisponivel:
                continue  # uma estacao fora do ar nao interrompe as demais (RNF05)
        return resultado

    def verificar_contrato(self) -> bool:
        try:
            fim = datetime.now(UTC)
            self.coletar_estacao(self._estacoes[0], fim - timedelta(hours=1), fim)
            return True
        except (ContratoQuebrado, FonteIndisponivel):
            return False
