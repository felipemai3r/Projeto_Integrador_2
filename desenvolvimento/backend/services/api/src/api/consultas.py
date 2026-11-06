"""Consultas reutilizadas pelos routers."""

from datetime import datetime, timedelta

from common.enums import Faixa, Qualidade, Variavel
from common.models import Estacao, Fonte, Leitura, Limiar
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import EstacaoOut, EstadoDado, Limiares


def obter_estacao(s: Session, codigo: str) -> Estacao | None:
    return s.scalar(select(Estacao).where(Estacao.codigo == codigo, Estacao.ativa))


def limiares_vigentes(s: Session, estacao_id: int) -> dict[Faixa, float]:
    """Limiar mais recente de cada faixa (a tabela guarda o historico, RN08)."""
    linhas = s.scalars(
        select(Limiar).where(Limiar.estacao_id == estacao_id).order_by(Limiar.vigente_desde.desc())
    )
    vigentes: dict[Faixa, float] = {}
    for li in linhas:
        faixa = Faixa(li.faixa)
        vigentes.setdefault(faixa, li.valor_m)
    return vigentes


def estacao_out(s: Session, e: Estacao) -> EstacaoOut:
    lim = limiares_vigentes(s, e.id)
    return EstacaoOut(
        codigo=e.codigo,
        nome=e.nome,
        curso_dagua=e.curso_dagua,
        papel=e.papel,
        latitude=e.latitude,
        longitude=e.longitude,
        limiares=Limiares(
            atencao=lim.get(Faixa.ATENCAO),
            alerta=lim.get(Faixa.ALERTA),
            alerta_alto=lim.get(Faixa.ALERTA_ALTO),
            extremo=lim.get(Faixa.EXTREMO),
        ),
    )


# Varias fontes medem o mesmo ponto (nivel do Ribeirao Revolver/Indios: GraphQL, REST e painel
# municipal), com instantes a segundos de distancia. Para a regra de alerta, a taxa e a serie,
# isso e UMA medicao: contar duas encurtaria a histerese (RN10) e dobraria pontos no grafico.
PRIORIDADE_FONTE = ("dcsc_graphql", "pdc_municipal", "dcsc_rest")
# Fontes de MEDICAO de chuva. A reanalise ERA5 (openmeteo_archive) tambem grava chuva_h001_mm,
# mas e estimativa de grade, nunca medicao: fica fora de tudo que se apresenta como medido.
FONTES_MEDIDAS = frozenset(PRIORIDADE_FONTE)
MESMO_INSTANTE = timedelta(seconds=150)  # metade do passo de 5 min; as fontes diferem por segundos
MAX_FONTES_POR_INSTANTE = 6  # folga para o limite de linhas lidas


def _prioridade(codigo: str) -> tuple[int, str]:
    """Desempate deterministico: fonte conhecida pela ordem acima; as demais, por codigo."""
    achado = PRIORIDADE_FONTE.index(codigo) if codigo in PRIORIDADE_FONTE else len(PRIORIDADE_FONTE)
    return (achado, codigo)


def _melhor(grupo: list[tuple[Leitura, str]]) -> tuple[Leitura, str]:
    return min(grupo, key=lambda x: (_prioridade(x[1]), -x[0].medido_em.timestamp()))


def uma_por_instante(linhas: list[tuple[Leitura, str]]) -> list[tuple[Leitura, str]]:
    """Reduz leituras (da mais nova para a mais antiga) a uma por instante de medicao.

    Junta num grupo as de FONTES DIFERENTES que estao a menos de MESMO_INSTANTE da mais nova do
    grupo e fica com a da fonte de maior prioridade. Duas leituras da mesma fonte nunca se juntam
    (sao instantes distintos, por proximos que sejam). Janela deslizante, e nao `date_bin`: com
    bins fixos, leituras 4 s separadas em torno de hh:mm:00 cairiam em bins distintos.
    """
    saida: list[tuple[Leitura, str]] = []
    grupo: list[tuple[Leitura, str]] = []
    for linha in linhas:
        if grupo and (
            grupo[0][0].medido_em - linha[0].medido_em >= MESMO_INSTANTE
            or any(g[1] == linha[1] for g in grupo)
        ):
            saida.append(_melhor(grupo))
            grupo = []
        grupo.append(linha)
    if grupo:
        saida.append(_melhor(grupo))
    return saida


def leituras_validas(
    s: Session,
    estacao_id: int,
    variavel: Variavel,
    *,
    ate: datetime | None = None,
    desde: datetime | None = None,
    n: int | None = None,
) -> list[tuple[Leitura, str]]:
    """Leituras validas (qualidade ok) sem duplicata de fonte, da mais nova para a mais antiga.

    Ponto unico de leitura de nivel/chuva para alertas, valor atual e serie. Com `n`, devolve as
    `n` mais recentes (instantes distintos).
    """
    q = (
        select(Leitura, Fonte.codigo)
        .join(Fonte, Fonte.id == Leitura.fonte_id)
        .where(
            Leitura.estacao_id == estacao_id,
            Leitura.variavel == variavel.value,
            Leitura.qualidade == Qualidade.OK.value,
            Leitura.valor.is_not(None),
        )
        .order_by(Leitura.medido_em.desc(), Fonte.codigo)
    )
    if ate is not None:
        q = q.where(Leitura.medido_em <= ate)
    if desde is not None:
        q = q.where(Leitura.medido_em >= desde)
    if n is not None:
        q = q.limit(n * MAX_FONTES_POR_INSTANTE + MAX_FONTES_POR_INSTANTE)
    unicas = uma_por_instante([(le, cod) for le, cod in s.execute(q).all()])
    return unicas[:n] if n is not None else unicas


def ultima_leitura(s: Session, estacao_id: int, variavel: Variavel) -> tuple[Leitura, str] | None:
    """Ultima leitura valida (qualidade ok) e o codigo da fonte."""
    achadas = leituras_validas(s, estacao_id, variavel, n=1)
    return achadas[0] if achadas else None


def serie_recente(
    s: Session, estacao_id: int, variavel: Variavel, ate: datetime, minutos: int
) -> list[tuple[datetime, float]]:
    """Serie dos ultimos `minutos` ate `ate`, em ordem cronologica, sem instantes repetidos."""
    achadas = leituras_validas(
        s, estacao_id, variavel, ate=ate, desde=ate - timedelta(minutes=minutos)
    )
    return [(le.medido_em, le.valor) for le, _ in reversed(achadas) if le.valor is not None]


def estado_do_dado(medido_em: datetime | None, agora: datetime, limite_min: int) -> EstadoDado:
    if medido_em is None:
        return "indisponivel"
    return "desatualizado" if agora - medido_em > timedelta(minutes=limite_min) else "ok"


def ultimas_leituras(
    s: Session, estacao_id: int, variavel: Variavel, n: int
) -> list[tuple[datetime, float]]:
    """As `n` leituras validas mais recentes (instantes distintos), da mais nova a mais antiga."""
    achadas = leituras_validas(s, estacao_id, variavel, n=n)
    return [(le.medido_em, le.valor) for le, _ in achadas if le.valor is not None]
