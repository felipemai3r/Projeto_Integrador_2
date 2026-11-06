"""Adaptador do GraphQL da Defesa Civil de SC (operacao Tags_data).

O servidor so aceita operacoes registradas: a consulta precisa ser enviada exatamente como o
portal envia (docs/fontes-de-dados.md, secao 3). Uma unica chamada traz todas as estacoes.
"""

from datetime import datetime
from typing import Any

import httpx
from common.enums import Variavel
from common.schemas import LeituraBruta

from ingestor.adapters.base import Adaptador
from ingestor.erros import ContratoQuebrado, FonteIndisponivel

QUERY_TAGS_DATA = """query Tags_data { tags_data(clients: ["secretaria-de-defesa-civil"]) {
  qualle_meteorologia { codigo name { prefix general local } timestamp
    position { bacia latitude longitude }
    data { rio { rio_nome { value } rio_nivel { value } }
           chuva { acumulado { h001 { value } h003 { value } h006 { value }
                               h012 { value } h024 { value } h048 { value }
                               h072 { value } h168 { value } } } } } } }"""

JANELAS_CHUVA = {
    "h001": Variavel.CHUVA_H001_MM,
    "h003": Variavel.CHUVA_H003_MM,
    "h006": Variavel.CHUVA_H006_MM,
    "h012": Variavel.CHUVA_H012_MM,
    "h024": Variavel.CHUVA_H024_MM,
    "h048": Variavel.CHUVA_H048_MM,
    "h072": Variavel.CHUVA_H072_MM,
    "h168": Variavel.CHUVA_H168_MM,
}


def _valor(no: Any) -> float | None:
    """Cada valor da fonte vem embrulhado em {'value': ...}."""
    if not isinstance(no, dict):
        return None
    v = no.get("value")
    return float(v) if isinstance(v, int | float) else None


def normalizar(resposta: dict[str, Any]) -> list[LeituraBruta]:
    """Converte a resposta do GraphQL em leituras internas. Funcao pura."""
    try:
        estacoes = resposta["data"]["tags_data"]["qualle_meteorologia"]
    except (KeyError, TypeError) as e:
        raise ContratoQuebrado(f"resposta sem data.tags_data.qualle_meteorologia: {e!r}") from e
    if not isinstance(estacoes, list):
        raise ContratoQuebrado("qualle_meteorologia nao e uma lista")

    leituras: list[LeituraBruta] = []
    for est in estacoes:
        codigo, ts = est.get("codigo"), est.get("timestamp")
        if not codigo or not ts:
            continue  # estacao sem leitura corrente
        try:
            medido_em = datetime.fromisoformat(ts)
        except (TypeError, ValueError) as e:
            raise ContratoQuebrado(f"{codigo}: timestamp invalido: {ts!r}") from e
        dados = est.get("data") or {}

        rio = dados.get("rio") or {}
        nivel = _valor(rio.get("rio_nivel"))
        if nivel is not None:
            leituras.append(
                LeituraBruta(
                    estacao_codigo=codigo,
                    variavel=Variavel.NIVEL_M,
                    valor=nivel,
                    unidade="m",
                    medido_em=medido_em,
                    bruto={"rio": rio},
                )
            )
        acumulado = ((dados.get("chuva") or {}).get("acumulado")) or {}
        for chave, variavel in JANELAS_CHUVA.items():
            valor = _valor(acumulado.get(chave))
            if valor is not None:
                leituras.append(
                    LeituraBruta(
                        estacao_codigo=codigo,
                        variavel=variavel,
                        valor=valor,
                        unidade="mm",
                        medido_em=medido_em,
                        bruto={chave: acumulado.get(chave)},
                    )
                )
    return leituras


class DcscGraphql(Adaptador):
    codigo = "dcsc_graphql"
    frequencia_s = 300

    def __init__(self, url: str, cliente: httpx.Client | None = None) -> None:
        self._url = url
        self._cliente = cliente or httpx.Client(timeout=30)

    def _buscar(self) -> dict[str, Any]:
        try:
            r = self._cliente.post(
                self._url,
                json={"operationName": "Tags_data", "query": QUERY_TAGS_DATA, "variables": {}},
            )
            r.raise_for_status()
            corpo: dict[str, Any] = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise FonteIndisponivel(f"{self.codigo}: {e!r}") from e
        if "errors" in corpo:
            raise ContratoQuebrado(f"{self.codigo}: {corpo['errors']!r}"[:500])
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
