import type { components } from './api-types'

export type EstacaoOut = components['schemas']['EstacaoOut']
export type NivelAtual = components['schemas']['NivelAtual']
export type ChuvaEstacao = components['schemas']['ChuvaEstacao']
export type Serie = components['schemas']['Serie']
export type Alerta = components['schemas']['AlertaOut']
export type Correlacao = components['schemas']['CorrelacaoOut']

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ErroApi extends Error {
  constructor(
    readonly status: number,
    mensagem: string,
  ) {
    super(mensagem)
  }
}

async function get<T>(caminho: string): Promise<T> {
  const resposta = await fetch(`${BASE}/api${caminho}`, { headers: { Accept: 'application/json' } })
  if (!resposta.ok) throw new ErroApi(resposta.status, `Falha ao consultar ${caminho}`)
  return (await resposta.json()) as T
}

export const api = {
  estacoes: () => get<EstacaoOut[]>('/estacoes'),
  nivelAtual: (codigo: string) => get<NivelAtual>(`/estacoes/${codigo}/atual`),
  chuvaAcumulada: () => get<ChuvaEstacao[]>('/chuva/acumulada'),
  alertasVigentes: () => get<Alerta[]>('/alertas?vigentes=true'),
  correlacao: () => get<Correlacao[]>('/correlacao'),
  serie: (codigo: string, horas: number) => get<Serie>(`/estacoes/${codigo}/serie?horas=${horas}`),
}
