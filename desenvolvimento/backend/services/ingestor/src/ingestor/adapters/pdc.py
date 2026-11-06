"""Adaptador da API do painel da Defesa Civil de Presidente Getulio (PDC).

Serie de 5 em 5 minutos, com historico desde 2025-09-13 (docs/fontes-de-dados.md, secao 8.1).
Armadilhas da fonte, todas confirmadas contra a API real:
- `sta_timestamp` vem em hora local (-03:00) mas rotulado +00:00, ou seja, 3h deslocado. O horario
  correto da medicao e `created_at` (UTC), que bate minuto a minuto com a API REST estadual.
- `rainfall_1h` e a chuva acumulada na ultima hora (janela movel), a mesma semantica do `h001` do
  GraphQL. Vai para CHUVA_H001_MM; nunca para CHUVA_ACUMULADA_MM, que e incremento de 5 minutos.
- O cursor da paginacao e inclusivo: a ultima linha de uma pagina reaparece no inicio da seguinte.
  Com limit=1 o cursor nunca avanca. Por isso deduplicamos por `id` e exigimos limite >= 2.
- Janela maxima de 31 dias por consulta e limite de 120 chamadas por minuto.
- Codigo de estacao desconhecido devolve 200 com lista vazia, nao erro.
"""

import logging
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from common.enums import Variavel
from common.schemas import LeituraBruta

from ingestor.adapters.base import Adaptador
from ingestor.erros import ChaveRecusada, ContratoQuebrado, FonteIndisponivel

log = logging.getLogger("ingestor.pdc")

# codigo na API do painel -> codigo no nosso banco. A Creche e a mesma estacao fisica da
# DCSC-00174 (coordenadas identicas), entao suas leituras vao para ela e nao ha estacao nova.
CODIGOS: dict[str, str] = {
    "DC-PEU-001": "DCSC-00174",
    "DC-PEU-002": "DC-PEU-002",
    "DC-PEU-003": "DC-PEU-003",
    "DC-PEU-004": "DC-PEU-004",
    "DCSC-00037": "DCSC-00037",
    "DCSC-00043": "DCSC-00043",
    "DCSC-00015": "DCSC-00015",
}

# campo da fonte -> (variavel interna, unidade). Os demais campos (temperatura, vento etc.) e os
# acumulados de 3h em diante vem nulos ou nao entram no modelo; ficam so no payload bruto.
CAMPOS: dict[str, tuple[Variavel, str]] = {
    "river_level": (Variavel.NIVEL_M, "m"),
    "rainfall_1h": (Variavel.CHUVA_H001_MM, "mm"),
}

# So estas estacoes tem regua de rio (o proprio painel marca "hasRiverSensor" so nelas). As demais
# mandam river_level quase sempre 0 com valores esporadicos de ate 42 m, que nao sao nivel de rio
# e contaminariam a serie (ver fontes-de-dados.md, secao 8.1).
COM_REGUA = {"DC-PEU-001", "DCSC-00043"}

JANELA_MAX = timedelta(days=31)
LIMITE_PAGINA = 1000
TENTATIVAS_429 = 3
ESPERA_429_MAX_S = 60.0
# 120 chamadas/min e o teto da fonte; 0,6 s entre chamadas da no maximo 100/min, com folga
INTERVALO_MIN_S = 0.6


def codigo_pdc(codigo: str) -> str:
    """Aceita o codigo da API do painel ou o do nosso banco e devolve o da API do painel."""
    for pdc, nosso in CODIGOS.items():
        if codigo in (pdc, nosso):
            return pdc
    raise KeyError(f"estacao sem mapeamento para a API do painel: {codigo}")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("datetime sem fuso")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def janelas(
    inicio: datetime, fim: datetime, tamanho: timedelta = JANELA_MAX
) -> Iterator[tuple[datetime, datetime]]:
    """Quebra [inicio, fim] em janelas consecutivas de no maximo `tamanho`. Funcao pura."""
    ini = inicio
    while ini < fim:
        fim_janela = min(ini + tamanho, fim)
        yield ini, fim_janela
        ini = fim_janela


def _registros(resposta: Any) -> list[dict[str, Any]]:
    if not isinstance(resposta, dict) or not isinstance(resposta.get("data"), list):
        raise ContratoQuebrado("pdc_municipal: resposta sem lista 'data'")
    return resposta["data"]


def normalizar(resposta: dict[str, Any]) -> list[LeituraBruta]:
    """Converte uma pagina de leituras em leituras internas. Funcao pura.

    Campo nulo e ignorado (a estacao nao mediu aquilo naquele instante). Falta do campo, e nao
    so valor nulo, significa que a fonte mudou o formato.
    """
    leituras: list[LeituraBruta] = []
    for reg in _registros(resposta):
        if not isinstance(reg, dict):
            raise ContratoQuebrado(f"pdc_municipal: registro nao e objeto: {reg!r}")
        codigo = reg.get("sta_code")
        if not isinstance(codigo, str) or not codigo:
            raise ContratoQuebrado(f"pdc_municipal: registro sem sta_code: {reg!r}")
        if not any(campo in reg for campo in CAMPOS):
            raise ContratoQuebrado(f"pdc_municipal {codigo}: registro sem {', '.join(CAMPOS)}")
        try:
            medido_em = datetime.fromisoformat(reg["created_at"])
        except (KeyError, TypeError, ValueError) as e:
            raise ContratoQuebrado(f"pdc_municipal {codigo}: created_at invalido: {e!r}") from e
        if medido_em.tzinfo is None:
            raise ContratoQuebrado(f"pdc_municipal {codigo}: created_at sem fuso")
        medido_em = medido_em.astimezone(UTC)
        bruto = {k: v for k, v in reg.items() if v is not None}
        for campo, (variavel, unidade) in CAMPOS.items():
            if variavel == Variavel.NIVEL_M and codigo not in COM_REGUA:
                continue
            valor = reg.get(campo)
            if isinstance(valor, int | float) and not isinstance(valor, bool):
                leituras.append(
                    LeituraBruta(
                        estacao_codigo=CODIGOS.get(codigo, codigo),
                        variavel=variavel,
                        valor=float(valor),
                        unidade=unidade,
                        medido_em=medido_em,
                        bruto=bruto,
                    )
                )
    return leituras


class Pdc(Adaptador):
    codigo = "pdc_municipal"
    frequencia_s = 300

    def __init__(
        self,
        base_url: str,
        chave: str,
        estacoes: list[str] | None = None,
        cliente: httpx.Client | None = None,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
        intervalo_min_s: float = INTERVALO_MIN_S,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._chave = chave
        # codigos da API do painel; sem lista, todas as estacoes mapeadas
        self._estacoes = [codigo_pdc(e) for e in estacoes] if estacoes else list(CODIGOS)
        self._cliente = cliente or httpx.Client(timeout=30)
        self._dormir = dormir
        self._relogio = relogio
        self._intervalo = intervalo_min_s
        self._ultima_chamada: float | None = None

    def _esperar_vez(self) -> None:
        """Espaca as chamadas para ficar abaixo do limite de 120 por minuto."""
        if self._ultima_chamada is not None:
            falta = self._intervalo - (self._relogio() - self._ultima_chamada)
            if falta > 0:
                self._dormir(falta)
        self._ultima_chamada = self._relogio()

    def _buscar(self, caminho: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET com chave, limite de taxa e nova tentativa em 429. Nunca registra a chave."""
        for tentativa in range(TENTATIVAS_429 + 1):
            self._esperar_vez()
            try:
                r = self._cliente.get(
                    f"{self._base}{caminho}", params=params, headers={"x-api-key": self._chave}
                )
            except httpx.HTTPError as e:
                raise FonteIndisponivel(f"{self.codigo}: {type(e).__name__}: {e}") from e
            if r.status_code == 429:
                if tentativa == TENTATIVAS_429:
                    raise FonteIndisponivel(f"{self.codigo}: limite de taxa (HTTP 429) persistente")
                espera = _espera_429(r, tentativa)
                log.warning(
                    "limite de taxa da fonte; aguardando",
                    extra={"extra_campos": {"fonte": self.codigo, "espera_s": espera}},
                )
                self._dormir(espera)
                continue
            if r.status_code in (401, 403):
                raise ChaveRecusada(f"{self.codigo}: chave recusada (HTTP {r.status_code})")
            if r.status_code >= 400:
                raise FonteIndisponivel(f"{self.codigo}: HTTP {r.status_code} em {caminho}")
            try:
                corpo = r.json()
            except ValueError as e:
                raise FonteIndisponivel(f"{self.codigo}: resposta nao e JSON") from e
            if not isinstance(corpo, dict):
                raise ContratoQuebrado(f"{self.codigo}: resposta nao e um objeto JSON")
            return corpo
        raise AssertionError("inalcancavel")  # pragma: no cover

    def _paginas(
        self, codigo: str, inicio: datetime, fim: datetime, limite: int, vistos: set[Any]
    ) -> list[dict[str, Any]]:
        """Todas as paginas de /readings de uma janela, sem repetir linhas (cursor inclusivo).

        `vistos` guarda os `id` ja lidos; e compartilhado entre janelas porque uma linha na
        fronteira de duas janelas pode vir nas duas.
        """
        registros: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {
                "code": codigo,
                "from": _iso(inicio),
                "to": _iso(fim),
                "limit": limite,
            }
            if cursor:
                params["cursor"] = cursor
            corpo = self._buscar("/readings", params)
            novos = 0
            for reg in _registros(corpo):
                chave = reg.get("id") if isinstance(reg, dict) else None
                if chave is None or chave not in vistos:
                    vistos.add(chave)
                    registros.append(reg)
                    novos += 1
            proximo = corpo.get("next_cursor")
            # sem cursor, ou cursor que nao avanca / pagina sem linha nova: terminou
            if not proximo or proximo == cursor or novos == 0:
                return registros
            cursor = str(proximo)

    def coletar_estacao(
        self, codigo: str, inicio: datetime, fim: datetime, limite: int = LIMITE_PAGINA
    ) -> list[LeituraBruta]:
        """Leituras de uma estacao (codigo da API do painel ou do nosso banco) em [inicio, fim].

        Janelas maiores que 31 dias sao quebradas em varias consultas.
        """
        if not 2 <= limite <= LIMITE_PAGINA:
            raise ValueError("limite deve ficar entre 2 e 1000 (com 1 o cursor nunca avanca)")
        pdc = codigo_pdc(codigo)
        registros: list[dict[str, Any]] = []
        vistos: set[Any] = set()
        for ini, fim_janela in janelas(inicio, fim):
            registros += self._paginas(pdc, ini, fim_janela, limite, vistos)
        return normalizar({"data": registros})

    def coletar(
        self, inicio: datetime | None = None, fim: datetime | None = None
    ) -> list[LeituraBruta]:
        fim = fim or datetime.now(UTC)
        inicio = inicio or fim - timedelta(hours=1)
        resultado: list[LeituraBruta] = []
        falhas: list[str] = []
        for codigo in self._estacoes:
            try:
                resultado += self.coletar_estacao(codigo, inicio, fim)
            except FonteIndisponivel as e:
                # uma estacao fora do ar nao interrompe as demais (RNF05)
                falhas.append(codigo)
                log.warning(
                    "estacao do painel indisponivel",
                    extra={
                        "extra_campos": {"fonte": self.codigo, "estacao": codigo, "erro": str(e)}
                    },
                )
        if falhas and len(falhas) == len(self._estacoes):
            # tudo falhou: nao pode virar coleta "vazia", o log de auditoria precisa ver a falha
            raise FonteIndisponivel(f"{self.codigo}: nenhuma estacao respondeu ({len(falhas)})")
        return resultado

    def verificar_contrato(self) -> bool:
        """Canario: /latest responde com o formato esperado e ao menos uma leitura."""
        try:
            return len(normalizar(self._buscar("/latest"))) > 0
        except (ContratoQuebrado, FonteIndisponivel):
            return False


def _espera_429(r: httpx.Response, tentativa: int) -> float:
    """Respeita Retry-After (segundos) quando vier; senao recua de forma progressiva."""
    try:
        espera = float(r.headers["retry-after"])
    except (KeyError, ValueError):
        espera = 5.0 * 2**tentativa
    return max(0.0, min(espera, ESPERA_429_MAX_S))
