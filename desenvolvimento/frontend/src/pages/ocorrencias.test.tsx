import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Moderacao } from './Moderacao'
import { Registrar } from './Registrar'

// O mapa (Leaflet) depende de layout real do navegador; aqui testamos o formulario.
vi.mock('../components/MapaBase', () => ({
  MapaBase: ({ children }: { children?: ReactNode }) => <div data-testid="mapa">{children}</div>,
  iconeDeMarcador: () => ({}),
}))
vi.mock('../components/SeletorDePonto', () => ({
  SeletorDePonto: ({ onChange }: { onChange: (p: { lat: number; lon: number }) => void }) => (
    <button type="button" onClick={() => onChange({ lat: -27.0455, lon: -49.6243 })}>
      marcar ponto de teste
    </button>
  ),
}))

function renderizar(ui: ReactNode) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const resposta = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } })

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('Registrar', () => {
  it('pede o ponto antes de enviar, sem chamar o servidor', async () => {
    const fetchFalso = vi.fn()
    vi.stubGlobal('fetch', fetchFalso)
    renderizar(<Registrar />)
    await userEvent.click(screen.getByRole('button', { name: 'Enviar registro' }))
    expect(screen.getByRole('alert')).toHaveTextContent('marcar onde alagou')
    expect(fetchFalso).not.toHaveBeenCalled()
  })

  it('pede o tipo de impacto depois do ponto', async () => {
    renderizar(<Registrar />)
    await userEvent.click(screen.getByRole('button', { name: 'marcar ponto de teste' }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar registro' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Escolha o que aconteceu')
  })

  it('envia o registro e explica que passa por conferencia, com o 199', async () => {
    const fetchFalso = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
      resposta({ id: 7, status: 'pendente', mensagem: 'Recebemos o seu registro.' }, 201),
    )
    vi.stubGlobal('fetch', fetchFalso)
    renderizar(<Registrar />)
    await userEvent.click(screen.getByRole('button', { name: 'marcar ponto de teste' }))
    await userEvent.click(screen.getByRole('radio', { name: /Água na calçada/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar registro' }))
    expect(await screen.findByText('Obrigado!')).toBeInTheDocument()
    expect(screen.getByText('199')).toBeInTheDocument()
    const corpo = fetchFalso.mock.calls[0]![1]!.body as FormData
    expect(corpo.get('tipo_impacto')).toBe('agua_calcada')
    expect(corpo.get('latitude')).toBe('-27.0455')
    expect(String(corpo.get('ocorreu_em'))).toMatch(/Z$/) // UTC, com fuso
  })

  it('mostra a mensagem do servidor quando o ponto esta fora do municipio', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        resposta({ detail: 'O ponto precisa estar dentro de Presidente Getúlio.' }, 422),
      ),
    )
    renderizar(<Registrar />)
    await userEvent.click(screen.getByRole('button', { name: 'marcar ponto de teste' }))
    await userEvent.click(screen.getByRole('radio', { name: /Outro/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar registro' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('dentro de Presidente Getúlio')
  })
})

describe('Moderacao', () => {
  it('mostra o login e informa erro de senha sem detalhar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => resposta({ detail: 'E-mail ou senha incorretos.' }, 401)),
    )
    renderizar(<Moderacao />)
    await userEvent.type(screen.getByLabelText('E-mail'), 'a@b.br')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.')
  })

  it('depois do login lista os pendentes e valida com um clique', async () => {
    const pendente = {
      id: 5,
      latitude: -27.04,
      longitude: -49.62,
      ocorreu_em: '2026-10-12T20:00:00Z',
      tipo_impacto: 'agua_imovel',
      descricao: 'Entrou água',
      tem_foto: false,
      status: 'pendente',
      contexto: { disponivel: true, niveis: { 'DCSC-00043': { nivel_m: 4.62 } }, chuva_24h_mm: {} },
      criada_em: '2026-10-12T20:05:00Z',
    }
    let pendentes = [pendente]
    const chamadas: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        chamadas.push(`${init?.method ?? 'GET'} ${url}`)
        if (url.includes('/auth/login'))
          return resposta({
            token: 't',
            nome: 'Leo',
            papel: 'moderador',
            expira_em: '2999-01-01T00:00:00Z',
          })
        if (init?.method === 'PATCH') {
          pendentes = []
          return resposta({ ...pendente, status: 'validada' })
        }
        return resposta(pendentes)
      }),
    )
    renderizar(<Moderacao />)
    await userEvent.type(screen.getByLabelText('E-mail'), 'leo@exemplo.br')
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-forte-123')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('Água dentro de imóvel')).toBeInTheDocument()
    expect(screen.getByText(/rio dos Índios em 4,62 m/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Validar' }))
    await waitFor(() => expect(screen.getByText(/Nenhum registro esperando/)).toBeInTheDocument())
    expect(chamadas.some((c) => c.startsWith('PATCH') && c.endsWith('/api/ocorrencias/5'))).toBe(
      true,
    )
  })

  it('rejeitar fica desabilitado sem motivo', async () => {
    const pendente = {
      id: 5,
      latitude: -27.04,
      longitude: -49.62,
      ocorreu_em: '2026-10-12T20:00:00Z',
      tipo_impacto: 'outro',
      descricao: null,
      tem_foto: false,
      status: 'pendente',
      contexto: null,
      criada_em: '2026-10-12T20:05:00Z',
    }
    sessionStorage.setItem(
      'fa-sessao',
      JSON.stringify({
        token: 't',
        nome: 'Leo',
        papel: 'moderador',
        expira_em: '2999-01-01T00:00:00Z',
      }),
    )
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => resposta([pendente])),
    )
    renderizar(<Moderacao />)
    const rejeitar = await screen.findByRole('button', { name: 'Rejeitar' })
    expect(rejeitar).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Motivo/), 'Duplicado')
    expect(rejeitar).toBeEnabled()
  })
})
