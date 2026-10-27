/**
 * Periodos dos filtros de tempo (grafico do nivel, mapa, relatorio). Uma definicao so, em horas,
 * para o mesmo seletor ter as mesmas opcoes e o mesmo texto em todo o sistema. 720 h e o maximo
 * que a API de series aceita.
 */
export const PERIODOS = [
  { valor: 1, rotulo: '1 hora' },
  { valor: 6, rotulo: '6 horas' },
  { valor: 24, rotulo: '24 horas' },
  { valor: 72, rotulo: '3 dias' },
  { valor: 168, rotulo: '7 dias' },
  { valor: 720, rotulo: '30 dias' },
]

export const PERIODO_PADRAO = 24

/** "última hora", "últimas 24 horas", "últimos 7 dias": para frases como "Período: ...". */
export function descreverPeriodo(horas: number): string {
  if (horas === 1) return 'última hora'
  const rotulo = PERIODOS.find((p) => p.valor === horas)?.rotulo ?? `${horas} horas`
  return `${horas >= 72 ? 'últimos' : 'últimas'} ${rotulo}`
}
