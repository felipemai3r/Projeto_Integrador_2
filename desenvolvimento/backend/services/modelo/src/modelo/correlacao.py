"""Correlacao defasada entre a chuva em cada ponto e a resposta do nivel na cidade (RF13).

Pergunta: que ponto antecipa o rio e com quantas horas de antecedencia?

Metodo:
- Resposta: variacao do nivel em 1 hora, em cm (nivel(t) - nivel(t-1h)). Diferenciar remove a
  tendencia e evita correlacao espuria entre duas series que apenas sobem juntas.
- Explicativa: chuva acumulada em uma janela (padrao 3 h) que TERMINA `d` horas antes de t.
  Defasagem d >= 1: so olha o passado, nunca o futuro.
- Medida: correlacao de Spearman (de postos). A chuva tem muitos zeros e cauda longa, e Spearman
  nao depende da forma da distribuicao.
- Significancia: teste de permutacao da estatistica "maior r entre todas as defasagens". A chuva
  e deslocada ciclicamente por um numero aleatorio de horas (preserva a autocorrelacao da chuva,
  mas quebra a relacao com o nivel) e o maior r entre as 36 defasagens e recalculado. O p-valor e
  a fracao de vezes em que o acaso iguala ou supera o r observado. Isso corrige o vies de
  "escolher o melhor de 36 e esquecer que escolhi": um IC do maximo seria sempre positivo.
- Incerteza do r: bootstrap em blocos de 24 h (dias inteiros) na defasagem escolhida. E um IC
  otimista por ter a defasagem escolhida nos mesmos dados; use o p-valor para decidir se ha sinal.

Limitacao declarada: poucos eventos fortes na base (docs/especificacao-completa.md, 9.5).
O resultado e exploratorio e diz quando nao ha sinal.
"""

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

log = logging.getLogger("modelo.correlacao")

METODO = (
    "Spearman entre a chuva acumulada na janela (terminando d horas antes) e a variacao "
    "horaria do nivel; p-valor por permutacao ciclica da estatistica do maximo entre as "
    "defasagens; IC por bootstrap em blocos de 24 h na defasagem escolhida"
)
DEFASAGENS_PADRAO = range(1, 37)
JANELA_PADRAO_H = 3
BLOCO_H = 24


@dataclass(frozen=True)
class PontoCurva:
    defasagem_h: int
    r: float | None
    n: int


@dataclass(frozen=True)
class ResultadoPonto:
    ponto: str
    explicativa: str
    janela_chuva_h: int
    melhor_defasagem_h: int
    r: float
    ic_inf: float | None
    ic_sup: float | None
    p_valor: float | None
    horas_validas: int
    curva: list[PontoCurva]

    @property
    def sinal_claro(self) -> bool:
        """Correlacao positiva e p < 0,05 no teste de permutacao do maximo."""
        return self.p_valor is not None and self.p_valor < 0.05 and self.r > 0


def delta_nivel_cm(nivel_horario: pd.Series) -> pd.Series:
    """Variacao do nivel na hora, em cm. NaN onde falta uma das duas pontas."""
    return nivel_horario.diff() * 100.0


def chuva_em_janela(chuva_horaria: pd.Series, janela_h: int) -> pd.Series:
    """Soma movel da chuva nas ultimas `janela_h` horas, ate a hora t inclusive. So passado."""
    return chuva_horaria.rolling(janela_h, min_periods=janela_h).sum()


def residuo_sem_chuva_local(
    delta: pd.Series, chuva_local: pd.Series, defasagens_locais: range = range(0, 4)
) -> pd.Series:
    """Parte da subida do nivel que a chuva LOCAL (defasagens 0 a 3 h) nao explica.

    Regressao linear em postos (ranks) de delta contra a chuva local nas defasagens dadas.
    O residuo, em postos, e a resposta que sobra para testar o efeito dos pontos a montante.
    """
    idx = delta.index
    X = pd.concat(
        [chuva_local.shift(d).reindex(idx).rename(f"l{d}") for d in defasagens_locais], axis=1
    )
    ok = X.notna().all(axis=1) & delta.notna()
    if int(ok.sum()) < 30:
        return pd.Series(np.nan, index=idx)
    y = delta[ok].rank().to_numpy()
    A = np.column_stack([np.ones(int(ok.sum()))] + [X.loc[ok, c].rank().to_numpy() for c in X])
    beta = np.linalg.lstsq(A, y, rcond=None)[0]
    return pd.Series(y - A @ beta, index=idx[ok]).reindex(idx)


def _spearman(a: np.ndarray, b: np.ndarray) -> tuple[float | None, int]:
    ok = ~(np.isnan(a) | np.isnan(b))
    n = int(ok.sum())
    if n < 30:
        return None, n
    ra = pd.Series(a[ok]).rank().to_numpy()
    rb = pd.Series(b[ok]).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return None, n
    return float(np.corrcoef(ra, rb)[0, 1]), n


def curva_de_correlacao(
    chuva_janela: pd.Series, delta: pd.Series, defasagens: range = DEFASAGENS_PADRAO
) -> list[PontoCurva]:
    """Correlacao para cada defasagem d: chuva_janela(t - d) contra delta(t)."""
    alvo = delta.to_numpy(dtype=float)
    saida: list[PontoCurva] = []
    for d in defasagens:
        explic = chuva_janela.shift(d).reindex(delta.index).to_numpy(dtype=float)
        r, n = _spearman(explic, alvo)
        saida.append(PontoCurva(d, r, n))
    return saida


def _melhor(curva: list[PontoCurva]) -> PontoCurva | None:
    validos = [p for p in curva if p.r is not None]
    return max(validos, key=lambda p: p.r) if validos else None  # type: ignore[arg-type,return-value]


def bootstrap_em_blocos(
    chuva_janela: pd.Series,
    delta: pd.Series,
    defasagem: int,
    repeticoes: int = 300,
    semente: int = 20260612,
) -> tuple[float | None, float | None]:
    """IC 95% do r em uma defasagem FIXA, reamostrando blocos de 24 h."""
    rng = np.random.default_rng(semente)
    idx = delta.index
    n_blocos = len(idx) // BLOCO_H
    if n_blocos < 5:
        return None, None
    explic = chuva_janela.shift(defasagem).reindex(idx).to_numpy(dtype=float)
    alvo = delta.to_numpy(dtype=float)
    rs: list[float] = []
    for _ in range(repeticoes):
        inicios = rng.integers(0, n_blocos, size=n_blocos) * BLOCO_H
        pos = (inicios[:, None] + np.arange(BLOCO_H)[None, :]).ravel()
        r, _ = _spearman(explic[pos], alvo[pos])
        if r is not None:
            rs.append(r)
    if len(rs) < repeticoes // 2:
        return None, None
    inf, sup = np.percentile(rs, [2.5, 97.5])
    return float(inf), float(sup)


def p_valor_do_maximo(
    chuva_janela: pd.Series,
    delta: pd.Series,
    r_observado: float,
    defasagens: range = DEFASAGENS_PADRAO,
    repeticoes: int = 200,
    semente: int = 20260612,
) -> float | None:
    """P(maior r entre as defasagens >= r_observado | nao ha relacao), por permutacao ciclica."""
    rng = np.random.default_rng(semente)
    idx = delta.index
    n = len(idx)
    if n < 24 * 7:
        return None
    base = chuva_janela.reindex(idx)
    alvo = delta.to_numpy(dtype=float)
    maiores = 0
    validas = 0
    for _ in range(repeticoes):
        deslocamento = int(rng.integers(BLOCO_H, n - BLOCO_H))
        embaralhada = pd.Series(np.roll(base.to_numpy(dtype=float), deslocamento), index=idx)
        maximo: float | None = None
        for d in defasagens:
            r, _ = _spearman(embaralhada.shift(d).to_numpy(dtype=float), alvo)
            if r is not None and (maximo is None or r > maximo):
                maximo = r
        if maximo is None:
            continue
        validas += 1
        maiores += maximo >= r_observado
    if validas < repeticoes // 2:
        return None
    return (1 + maiores) / (1 + validas)


def analisar_ponto(
    ponto: str,
    chuva_horaria: pd.Series,
    delta: pd.Series,
    janela_h: int = JANELA_PADRAO_H,
    explicativa: str = "chuva",
    defasagens: range = DEFASAGENS_PADRAO,
    repeticoes: int = 200,
) -> ResultadoPonto | None:
    """Analise completa de um ponto. Devolve None se nao ha dados suficientes."""
    chuva_janela = chuva_em_janela(chuva_horaria, janela_h)
    curva = curva_de_correlacao(chuva_janela, delta, defasagens)
    melhor = _melhor(curva)
    if melhor is None or melhor.r is None:
        return None
    inf, sup = bootstrap_em_blocos(chuva_janela, delta, melhor.defasagem_h, repeticoes)
    p = p_valor_do_maximo(chuva_janela, delta, melhor.r, defasagens, repeticoes)
    return ResultadoPonto(
        ponto=ponto,
        explicativa=explicativa,
        janela_chuva_h=janela_h,
        melhor_defasagem_h=melhor.defasagem_h,
        r=melhor.r,
        ic_inf=inf,
        ic_sup=sup,
        p_valor=p,
        horas_validas=melhor.n,
        curva=curva,
    )


def formatar(resultados: list[ResultadoPonto]) -> str:
    linhas = [
        f"{'ponto':<12}{'defasagem':>10}{'r':>8}{'IC 95% (otimista)':>22}"
        f"{'p':>8}{'horas':>8}  leitura",
        "-" * 92,
    ]
    for r in sorted(resultados, key=lambda x: -x.r):
        ic = f"[{r.ic_inf:+.2f}; {r.ic_sup:+.2f}]" if r.ic_inf is not None else "n/d"
        p = f"{r.p_valor:.3f}" if r.p_valor is not None else "n/d"
        leitura = "sinal" if r.sinal_claro else "sem sinal claro (p >= 0,05)"
        linhas.append(
            f"{r.ponto:<12}{r.melhor_defasagem_h:>8} h{r.r:>+8.2f}{ic:>22}{p:>8}"
            f"{r.horas_validas:>8}  {leitura}"
        )
    return "\n".join(linhas)


def principal() -> None:
    from common.config import obter_configuracao
    from common.db import sessao
    from common.logs import configurar
    from common.models import Correlacao, Estacao
    from sqlalchemy import select

    from modelo.dados import chuva_horaria, nivel_horario

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--estacao", default="DCSC-00043", help="estacao alvo (nivel)")
    ap.add_argument("--janela", type=int, default=JANELA_PADRAO_H, help="janela de chuva, em horas")
    ap.add_argument("--dias", type=int, default=90)
    ap.add_argument("--repeticoes", type=int, default=200)
    ap.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    ap.add_argument("--sem-salvar", action="store_true")
    args = ap.parse_args()
    configurar(obter_configuracao().log_level)

    fim = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    inicio = fim - timedelta(days=args.dias)
    resultados: list[ResultadoPonto] = []
    with sessao() as s:
        alvo = s.scalar(select(Estacao).where(Estacao.codigo == args.estacao))
        if alvo is None:
            raise SystemExit(f"estacao {args.estacao} nao encontrada")
        delta = delta_nivel_cm(nivel_horario(s, args.estacao, inicio, fim))
        pontos = s.scalars(
            select(Estacao).where(
                Estacao.ativa, Estacao.papel.in_(["alvo", "influencia", "referencia"])
            )
        ).all()
        chuvas = {p.codigo: chuva_horaria(s, p.codigo, inicio, fim) for p in pontos}
        sem_local = (
            residuo_sem_chuva_local(delta, chuvas[args.estacao])
            if not chuvas.get(args.estacao, pd.Series(dtype=float)).empty
            else None
        )
        niveis = {
            p.codigo: delta_nivel_cm(nivel_horario(s, p.codigo, inicio, fim))
            for p in pontos
            if p.codigo != args.estacao
        }

        def guardar(res: ResultadoPonto | None, ponto_id: int) -> None:
            if res is None:
                return
            resultados.append(res)
            if not args.sem_salvar:
                s.add(
                    Correlacao(
                        estacao_alvo_id=alvo.id,
                        ponto_id=ponto_id,
                        explicativa=res.explicativa,
                        janela_chuva_h=res.janela_chuva_h,
                        melhor_defasagem_h=res.melhor_defasagem_h,
                        r=res.r,
                        ic_inf=res.ic_inf,
                        ic_sup=res.ic_sup,
                        p_valor=res.p_valor,
                        horas_validas=res.horas_validas,
                        curva=[asdict(c) for c in res.curva],
                        metodo=METODO,
                        periodo_inicio=inicio,
                        periodo_fim=fim,
                    )
                )

        for p in pontos:
            if not chuvas[p.codigo].empty:
                guardar(
                    analisar_ponto(
                        p.codigo,
                        chuvas[p.codigo],
                        delta,
                        args.janela,
                        "chuva_bruta",
                        repeticoes=args.repeticoes,
                    ),
                    p.id,
                )
                if sem_local is not None and p.codigo != args.estacao:
                    guardar(
                        analisar_ponto(
                            p.codigo,
                            chuvas[p.codigo],
                            sem_local,
                            args.janela,
                            "chuva_sem_local",
                            repeticoes=args.repeticoes,
                        ),
                        p.id,
                    )
            # propagacao do nivel: a subida do rio nesse ponto antecipa a da cidade?
            if p.codigo in niveis and niveis[p.codigo].notna().sum() > 24 * 7:
                guardar(
                    analisar_ponto(
                        p.codigo,
                        niveis[p.codigo],
                        delta,
                        1,
                        "nivel",
                        repeticoes=args.repeticoes,
                    ),
                    p.id,
                )
    if args.json:
        print(json.dumps([asdict(r) for r in resultados], indent=1))
    else:
        periodo = f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"
        print(f"Alvo: {args.estacao} | periodo: {periodo} | janela de chuva: {args.janela} h")
        titulos = {
            "chuva_bruta": "1) Chuva em cada ponto x subida do nivel na cidade",
            "chuva_sem_local": "2) Chuva a montante, DESCONTADA a chuva local (efeito adicional)",
            "nivel": "3) Subida do nivel nos outros rios x subida do nivel na cidade",
        }
        for chave, titulo in titulos.items():
            grupo = [r for r in resultados if r.explicativa == chave]
            if grupo:
                print(f"\n{titulo}\n{formatar(grupo)}")


if __name__ == "__main__":
    principal()
