import type { components } from './api-types'

export type EstacaoOut = components['schemas']['EstacaoOut']
export type NivelAtual = components['schemas']['NivelAtual']
export type ChuvaEstacao = components['schemas']['ChuvaEstacao']
export type Serie = components['schemas']['Serie']
export type Alerta = components['schemas']['AlertaOut']
export type Correlacao = components['schemas']['CorrelacaoOut']

const BASE = import.meta.env.VITE_API_BASE ?? ''

export type OcorrenciaOut = components['schemas']['OcorrenciaOut']
export type TokenOut = components['schemas']['TokenOut']
export type ModeracaoOut = components['schemas']['ModeracaoOut']

export class ErroApi extends Error {
  constructor(
    readonly status: number,
    mensagem: string,
  ) {
    super(mensagem)
  }
}

async function pedir<T>(caminho: string, init: RequestInit = {}, token?: string): Promise<T> {
  const cabecalhos = new Headers(init.headers)
  cabecalhos.set('Accept', 'application/json')
  if (token) cabecalhos.set('Authorization', `Bearer ${token}`)
  const resposta = await fetch(`${BASE}/api${caminho}`, { ...init, headers: cabecalhos })
  if (!resposta.ok) {
    let detalhe = `Falha ao consultar ${caminho}`
    try {
      const corpo = (await resposta.json()) as { detail?: unknown }
      if (typeof corpo.detail === 'string') detalhe = corpo.detail
    } catch {
      /* corpo sem JSON: fica a mensagem generica */
    }
    throw new ErroApi(resposta.status, detalhe)
  }
  return (await resposta.json()) as T
}

const get = <T>(caminho: string, token?: string) => pedir<T>(caminho, {}, token)

export const api = {
  estacoes: () => get<EstacaoOut[]>('/estacoes'),
  nivelAtual: (codigo: string) => get<NivelAtual>(`/estacoes/${codigo}/atual`),
  chuvaAcumulada: () => get<ChuvaEstacao[]>('/chuva/acumulada'),
  alertasVigentes: () => get<Alerta[]>('/alertas?vigentes=true'),
  correlacao: () => get<Correlacao[]>('/correlacao'),
  serie: (codigo: string, horas: number) => get<Serie>(`/estacoes/${codigo}/serie?horas=${horas}`),
  contorno: () => get<GeoJSON.FeatureCollection>('/municipio'),
  ocorrencias: (dias: number) => get<OcorrenciaOut[]>(`/ocorrencias?dias=${dias}`),
  registrarOcorrencia: (dados: FormData) =>
    pedir<{ id: number; status: string; mensagem: string }>('/ocorrencias', {
      method: 'POST',
      body: dados,
    }),
  login: (email: string, senha: string) =>
    pedir<TokenOut>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, senha }),
    }),
  pendentes: (token: string) => get<OcorrenciaOut[]>('/ocorrencias?status=pendente', token),
  moderar: (
    token: string,
    id: number,
    corpo: { acao: string; tipo_impacto?: string; nota?: string },
  ) =>
    pedir<OcorrenciaOut>(
      `/ocorrencias/${id}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(corpo),
      },
      token,
    ),
  historico: (token: string, id: number) =>
    get<ModeracaoOut[]>(`/ocorrencias/${id}/historico`, token),
  pushChave: () => get<{ configurado: boolean; chave_publica: string }>('/push/chave'),
  inscrever: (corpo: {
    endpoint: string
    keys: { p256dh: string; auth: string }
    estacao: string | null
    faixa_minima: string
  }) =>
    pedir<{ status: string }>('/inscricoes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo),
    }),
  cancelarInscricao: (endpoint: string) =>
    pedir<{ status: string }>('/inscricoes', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint }),
    }),
  fotoProtegida: async (token: string, id: number): Promise<string> => {
    const r = await fetch(`${BASE}/api/ocorrencias/${id}/foto`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!r.ok) throw new ErroApi(r.status, 'Foto indisponível')
    return URL.createObjectURL(await r.blob())
  },
}
