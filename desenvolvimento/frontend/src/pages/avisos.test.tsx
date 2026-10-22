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

describe('Avisos por e-mail', () => {
  it('envia o pedido e explica que falta confirmar pelo link', async () => {
    const fetchFalso = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
      resposta({ status: 'pendente', mensagem: 'Enviamos um link para o seu e-mail.' }, 202),
    )
    vi.stubGlobal('fetch', fetchFalso)
    renderizar()
    await userEvent.type(screen.getByLabelText('Seu e-mail'), 'ana@exemplo.br')
    await userEvent.click(screen.getByRole('button', { name: 'Receber avisos por e-mail' }))
    expect(await screen.findByText('Enviamos um link para o seu e-mail.')).toBeInTheDocument()
    const [url, init] = fetchFalso.mock.calls[0]!
    expect(url).toContain('/api/inscricoes/email')
    expect(JSON.parse(init!.body as string)).toEqual({
      email: 'ana@exemplo.br',
      estacao: 'DCSC-00043',
      faixa_minima: 'atencao',
    })
  })

  it('confirma pelo link do e-mail com um POST', async () => {
    const fetchFalso = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
      resposta({ status: 'confirmado', mensagem: 'Pronto! Os avisos por e-mail estão ativos.' }),
    )
    vi.stubGlobal('fetch', fetchFalso)
    renderizar('/avisos?confirmar=abc')
    expect(
      await screen.findByText('Pronto! Os avisos por e-mail estão ativos.'),
    ).toBeInTheDocument()
    expect(fetchFalso).toHaveBeenCalledTimes(1)
    expect(fetchFalso.mock.calls[0]![0]).toContain('/api/inscricoes/email/confirmar')
    expect(fetchFalso.mock.calls[0]![1]!.method).toBe('POST')
  })
})
