import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Previsao } from './Previsao'

const resposta = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } })

const horizonte = (h: number, extra: object = {}) => ({
  horizonte_h: h,
  disponivel: false,
  motivo:
    'A previsão ainda não está disponível. Só há 53 dias de dados completos; o mínimo para publicar é 60.',
  valido_para: null,
  nivel_m: null,
  incerteza_m: null,
  intervalo_m: null,
  faixa: null,
  modelo: null,
  extrapolacao: [],
  ...extra,
})

const base = {
  estacao: 'DCSC-00043',
  origem: 'operacional',
  base_em: '2026-10-13T00:00:00Z',
  nivel_base_m: 1.78,
  aviso: 'Estimativa de apoio.',
}

function renderizar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <Previsao />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Previsao', () => {
  it('sem modelo publicado explica por que e nao mostra nenhum numero de previsao', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        resposta({ ...base, horizontes: [1, 3, 6, 12, 24].map((h) => horizonte(h)) }),
      ),
    )
    renderizar()
    expect(
      await screen.findByText(/A previsão ainda não está disponível\. Precisamos de mais dados/),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/mínimo para publicar é 60/)).toHaveLength(5)
    expect(screen.queryByText(/95% de confiança/)).not.toBeInTheDocument()
  })

  it('horizonte publicado mostra nivel, intervalo, faixa e rotula como previsao', async () => {
    const h3 = horizonte(3, {
      disponivel: true,
      motivo: null,
      valido_para: '2026-10-13T03:00:00Z',
      nivel_m: 4.62,
      incerteza_m: 0.2,
      intervalo_m: [4.42, 4.82],
      faixa: 'atencao',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => resposta({ ...base, horizontes: [horizonte(1), h3] })),
    )
    renderizar()
    expect(await screen.findByText('4,62')).toBeInTheDocument()
    expect(screen.getByText(/Entre 4,42 e 4,82 m \(95% de\s*confiança\)/)).toBeInTheDocument()
    expect(screen.getByText(/Atenção \(previsão\)/)).toBeInTheDocument()
  })

  it('simulador valida o campo antes de chamar o servidor', async () => {
    const f = vi.fn(async () => resposta({ ...base, horizontes: [] }))
    vi.stubGlobal('fetch', f)
    renderizar()
    await screen.findByText('Previsão do nível')
    const chamadasIniciais = f.mock.calls.length
    await userEvent.click(screen.getByRole('button', { name: 'Simular' }))
    expect(screen.getByRole('alert')).toHaveTextContent('pelo menos um ponto')
    await userEvent.type(screen.getByLabelText(/Dona Emma/), '900')
    await userEvent.click(screen.getByRole('button', { name: 'Simular' }))
    expect(screen.getByRole('alert')).toHaveTextContent('entre 0 e 400 mm')
    expect(f.mock.calls.length).toBe(chamadasIniciais)
  })

  it('cenario vem marcado como hipotetico e nao como previsao', async () => {
    const f = vi.fn(async (url: string) =>
      url.includes('/simulacao')
        ? resposta({
            ...base,
            origem: 'cenario',
            horizontes: [
              horizonte(3, {
                disponivel: true,
                motivo: null,
                nivel_m: 5.1,
                incerteza_m: 0.3,
                intervalo_m: [4.8, 5.4],
                faixa: 'atencao',
                extrapolacao: ['chuva_local_1h'],
              }),
            ],
          })
        : resposta({ ...base, horizontes: [] }),
    )
    vi.stubGlobal('fetch', f)
    renderizar()
    await screen.findByText('Previsão do nível')
    await userEvent.type(screen.getByLabelText(/Dona Emma/), '50')
    await userEvent.click(screen.getByRole('button', { name: 'Simular' }))
    expect(await screen.findByText('Cenário hipotético. Não é uma previsão.')).toBeInTheDocument()
    expect(screen.getByText(/Atenção \(cenário\)/)).toBeInTheDocument()
    expect(screen.getByText(/fora do que já foi observado/)).toBeInTheDocument()
  })
})
