import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ErroApi } from './api'

const json = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } })

let fetchFalso: ReturnType<typeof vi.fn>

function chamada(i = 0): { url: string; init: RequestInit; cab: Headers } {
  const [url, init] = fetchFalso.mock.calls[i] as [string, RequestInit]
  return { url, init, cab: new Headers(init.headers) }
}

beforeEach(() => {
  fetchFalso = vi.fn(async () => json({}))
  vi.stubGlobal('fetch', fetchFalso)
})
afterEach(() => vi.unstubAllGlobals())

describe('pedidos de leitura', () => {
  it('pede JSON e monta a URL com o prefixo /api', async () => {
    await api.estacoes()
    const { url, cab, init } = chamada()
    expect(url).toBe('/api/estacoes')
    expect(cab.get('Accept')).toBe('application/json')
    expect(cab.has('Authorization')).toBe(false)
    expect(init.method).toBeUndefined()
  })

  it('serie leva o codigo e as horas na URL', async () => {
    await api.serie('DCSC-00174', 168)
    expect(chamada().url).toBe('/api/estacoes/DCSC-00174/serie?horas=168')
  })

  it('previsao e nivel atual usam o codigo da estacao', async () => {
    await api.previsao('DCSC-00174')
    await api.nivelAtual('DC-PEU-002')
    expect(chamada(0).url).toBe('/api/previsao/DCSC-00174')
    expect(chamada(1).url).toBe('/api/estacoes/DC-PEU-002/atual')
  })

  it('mapa pede tambem os registros pendentes', async () => {
    await api.ocorrencias(24)
    expect(chamada().url).toBe('/api/ocorrencias?horas=24&com_pendentes=true')
  })

  it('alertas vigentes e historico usam filtros diferentes', async () => {
    await api.alertasVigentes()
    await api.alertasHistorico()
    expect(chamada(0).url).toBe('/api/alertas?vigentes=true')
    expect(chamada(1).url).toBe('/api/alertas?limite=200')
  })

  it('devolve o corpo ja convertido', async () => {
    fetchFalso.mockResolvedValueOnce(json([{ codigo: 'X' }]))
    expect(await api.estacoes()).toEqual([{ codigo: 'X' }])
  })
})

describe('autenticacao', () => {
  it('rotas de moderacao enviam o token como Bearer', async () => {
    await api.pendentes('abc.def.ghi')
    const { url, cab } = chamada()
    expect(url).toBe('/api/ocorrencias?status=pendente')
    expect(cab.get('Authorization')).toBe('Bearer abc.def.ghi')
  })

  it('moderar envia PATCH com JSON e token', async () => {
    await api.moderar('tk', 12, { acao: 'validar' })
    const { url, init, cab } = chamada()
    expect(url).toBe('/api/ocorrencias/12')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual({ acao: 'validar' })
    expect(cab.get('Content-Type')).toBe('application/json')
    expect(cab.get('Authorization')).toBe('Bearer tk')
  })

  it('login nao envia Authorization', async () => {
    await api.login('a@b.c', 'senha')
    const { init, cab } = chamada()
    expect(init.method).toBe('POST')
    expect(cab.has('Authorization')).toBe(false)
    expect(JSON.parse(init.body as string)).toEqual({ email: 'a@b.c', senha: 'senha' })
  })
})

describe('corpos e metodos de escrita', () => {
  it('simular manda a estacao, a janela e a chuva por ponto', async () => {
    await api.simular({ chuva_mm: { 'DCSC-00043': 30 }, janela_h: 6, estacao: 'DCSC-00043' })
    const { url, init } = chamada()
    expect(url).toBe('/api/simulacao')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      chuva_mm: { 'DCSC-00043': 30 },
      janela_h: 6,
      estacao: 'DCSC-00043',
    })
  })

  it('curtir usa POST e desfazer usa DELETE na mesma rota', async () => {
    const corpo = { tipo: 'curtida', dispositivo: 'd1' }
    await api.reagir(5, corpo)
    await api.desfazerReacao(5, corpo)
    expect(chamada(0).url).toBe('/api/ocorrencias/5/reacoes')
    expect(chamada(0).init.method).toBe('POST')
    expect(chamada(1).url).toBe('/api/ocorrencias/5/reacoes')
    expect(chamada(1).init.method).toBe('DELETE')
  })

  it('registrar ocorrencia envia FormData sem fixar o Content-Type', async () => {
    const dados = new FormData()
    dados.append('latitude', '-27.04')
    await api.registrarOcorrencia(dados)
    const { init, cab } = chamada()
    expect(init.body).toBe(dados)
    expect(cab.has('Content-Type')).toBe(false) // o navegador acrescenta o boundary
  })

  it('cancelar inscricao por e-mail envia so o token', async () => {
    await api.cancelarEmail('tok')
    expect(JSON.parse(chamada().init.body as string)).toEqual({ token: 'tok' })
    expect(chamada().url).toBe('/api/inscricoes/email/cancelar')
  })
})

describe('erros', () => {
  it('resposta nao ok vira ErroApi com o status e a mensagem do servidor', async () => {
    fetchFalso.mockResolvedValueOnce(json({ detail: 'Ponto fora do município.' }, 422))
    const erro = await api.registrarOcorrencia(new FormData()).catch((e: unknown) => e)
    expect(erro).toBeInstanceOf(ErroApi)
    expect(erro).toBeInstanceOf(Error)
    expect((erro as ErroApi).status).toBe(422)
    expect((erro as ErroApi).message).toBe('Ponto fora do município.')
  })

  it('detalhe que nao e texto (lista de validacao) cai na mensagem generica', async () => {
    fetchFalso.mockResolvedValueOnce(json({ detail: [{ msg: 'x', loc: ['body'] }] }, 422))
    await expect(api.estacoes()).rejects.toMatchObject({
      status: 422,
      message: 'Falha ao consultar /estacoes',
    })
  })

  it('corpo sem JSON (pagina de erro do proxy) cai na mensagem generica', async () => {
    fetchFalso.mockResolvedValueOnce(new Response('<html>502</html>', { status: 502 }))
    await expect(api.estacoes()).rejects.toMatchObject({
      status: 502,
      message: 'Falha ao consultar /estacoes',
    })
  })

  it('401 e 429 chegam ao chamador com o status, para a tela decidir o que dizer', async () => {
    fetchFalso.mockResolvedValueOnce(json({ detail: 'Entre para continuar.' }, 401))
    await expect(api.pendentes('x')).rejects.toMatchObject({ status: 401 })
    fetchFalso.mockResolvedValueOnce(json({ detail: 'Muitas tentativas.' }, 429))
    await expect(api.login('a', 'b')).rejects.toMatchObject({
      status: 429,
      message: 'Muitas tentativas.',
    })
  })

  it('falha de rede propaga o erro do fetch', async () => {
    fetchFalso.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api.estacoes()).rejects.toThrow('Failed to fetch')
  })
})

describe('fotoProtegida', () => {
  it('pede com token e devolve uma URL local do arquivo', async () => {
    const original = URL.createObjectURL
    const criar = vi.fn(() => 'blob:foto-1')
    URL.createObjectURL = criar
    try {
      fetchFalso.mockResolvedValueOnce(new Response(new Blob(['x']), { status: 200 }))
      expect(await api.fotoProtegida('tk', 9)).toBe('blob:foto-1')
      expect(criar).toHaveBeenCalledTimes(1)
    } finally {
      URL.createObjectURL = original
    }
    const { url, cab } = chamada()
    expect(url).toBe('/api/ocorrencias/9/foto')
    expect(cab.get('Authorization')).toBe('Bearer tk')
  })

  it('foto negada vira ErroApi "Foto indisponível" com o status', async () => {
    fetchFalso.mockResolvedValueOnce(new Response('', { status: 403 }))
    await expect(api.fotoProtegida('tk', 9)).rejects.toMatchObject({
      status: 403,
      message: 'Foto indisponível',
    })
  })
})
