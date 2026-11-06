import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Avisos } from './Avisos'

const resposta = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } })

function renderizar(url = '/avisos') {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[url]}>
        <Avisos />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

const ESTACOES = [
  {
    codigo: 'DCSC-00043',
    nome: 'PCD Presidente Getúlio',
    curso_dagua: 'Rio dos Índios',
    papel: 'alvo',
  },
  { codigo: 'DCSC-00174', nome: 'PCD ZAS Creche', curso_dagua: 'Ribeirão Revólver', papel: 'alvo' },
  {
    codigo: 'DCSC-00021',
    nome: 'PCD José Boiteux',
    curso_dagua: 'Rio Itajaí do Norte',
    papel: 'influencia',
  },
  { codigo: 'DC-PEU-002', nome: 'PCD Serra Mirador', curso_dagua: null, papel: 'influencia' },
]

/** Responde /estacoes com o cadastro e qualquer outra rota com `outra`. */
function servidor(outra: () => Response) {
  return vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) =>
    url.includes('/api/estacoes') ? resposta(ESTACOES) : outra(),
  )
}

const chamadasDe = (f: ReturnType<typeof servidor>, trecho: string) =>
  f.mock.calls.filter(([url]) => url.includes(trecho))

describe('Avisos por e-mail', () => {
  it('envia o pedido e explica que falta confirmar pelo link', async () => {
    const fetchFalso = servidor(() =>
      resposta({ status: 'pendente', mensagem: 'Enviamos um link para o seu e-mail.' }, 202),
    )
    vi.stubGlobal('fetch', fetchFalso)
    renderizar()
    await screen.findByRole('option', { name: 'Rio dos Índios' })
    await userEvent.type(screen.getByLabelText('Seu e-mail'), 'ana@exemplo.br')
    await userEvent.click(screen.getByRole('button', { name: 'Receber avisos por e-mail' }))
    expect(await screen.findByText('Enviamos um link para o seu e-mail.')).toBeInTheDocument()
    const [url, init] = chamadasDe(fetchFalso, '/api/inscricoes/email')[0]!
    expect(url).toContain('/api/inscricoes/email')
    expect(JSON.parse(init!.body as string)).toEqual({
      email: 'ana@exemplo.br',
      estacao: 'DCSC-00043',
      faixa_minima: 'alerta',
    })
  })

  it('confirma pelo link do e-mail com um POST', async () => {
    const fetchFalso = servidor(() =>
      resposta({ status: 'confirmado', mensagem: 'Pronto! Os avisos por e-mail estão ativos.' }),
    )
    vi.stubGlobal('fetch', fetchFalso)
    renderizar('/avisos?confirmar=abc')
    expect(
      await screen.findByText('Pronto! Os avisos por e-mail estão ativos.'),
    ).toBeInTheDocument()
    const confirmacoes = chamadasDe(fetchFalso, '/api/inscricoes/email')
    expect(confirmacoes).toHaveLength(1)
    expect(confirmacoes[0]![0]).toContain('/api/inscricoes/email/confirmar')
    expect(confirmacoes[0]![1]!.method).toBe('POST')
  })

  it('monta as opcoes de rio com as estacoes alvo da API, mais "todos"', async () => {
    vi.stubGlobal(
      'fetch',
      servidor(() => resposta({}, 404)),
    )
    renderizar()
    await screen.findByRole('option', { name: 'Ribeirão Revólver' })
    const opcoes = screen.getAllByRole('option').map((o) => (o as HTMLOptionElement).value)
    const rios = screen.getAllByRole('combobox', { name: 'Qual rio' })[0]!
    expect(rios).toHaveValue('DCSC-00043') // padrao continua sendo o Indios
    // so alvos: nada de ponto de influencia nem estacao so de chuva
    expect(opcoes).toEqual(expect.arrayContaining(['DCSC-00043', 'DCSC-00174', '']))
    expect(opcoes).not.toContain('DCSC-00021')
    expect(opcoes).not.toContain('DC-PEU-002')
  })

  it('permite assinar o Ribeirao Revolver', async () => {
    const fetchFalso = servidor(() =>
      resposta({ status: 'pendente', mensagem: 'Enviamos um link para o seu e-mail.' }, 202),
    )
    vi.stubGlobal('fetch', fetchFalso)
    renderizar()
    await screen.findByRole('option', { name: 'Ribeirão Revólver' })
    await userEvent.type(screen.getByLabelText('Seu e-mail'), 'ana@exemplo.br')
    await userEvent.selectOptions(
      screen.getAllByRole('combobox', { name: 'Qual rio' })[0]!,
      'DCSC-00174',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Receber avisos por e-mail' }))
    await screen.findByText('Enviamos um link para o seu e-mail.')
    const [, init] = chamadasDe(fetchFalso, '/api/inscricoes/email')[0]!
    expect(JSON.parse(init!.body as string)).toMatchObject({ estacao: 'DCSC-00174' })
  })

  it('se o cadastro nao carregar, ainda oferece "Todos os rios"', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => resposta({ detail: 'x' }, 500)),
    )
    renderizar()
    expect(await screen.findByRole('option', { name: 'Todos os rios' })).toBeInTheDocument()
  })
})
