import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ComoFunciona } from './ComoFunciona'

function renderizar(corpo: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(corpo), { status: 200 })),
  )
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter>
        <ComoFunciona />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const base = {
  nome: 'SDC-SC Dona Emma',
  ic_inf: 0,
  ic_sup: 0.2,
  horas_validas: 1900,
  leitura: '',
  janela_chuva_h: 3,
  periodo_inicio: '2026-07-15T00:00:00Z',
  periodo_fim: '2026-10-13T00:00:00Z',
  calculado_em: '2026-10-13T00:00:00Z',
}

afterEach(() => vi.unstubAllGlobals())

describe('ComoFunciona', () => {
  it('explica as faixas com texto e nao so cor, e lembra que nao substitui a Defesa Civil', async () => {
    renderizar([])
    expect(screen.getByText(/Não substitui a Defesa Civil/i)).toBeInTheDocument()
    expect(screen.getAllByText('Atenção').length).toBeGreaterThan(0)
    expect(await screen.findByText(/ainda não foi calculada/)).toBeInTheDocument()
  })

  it('sem relacao clara a montante, diz isso sem exagerar e sem descartar a hipotese', async () => {
    renderizar([
      {
        ...base,
        ponto: 'DCSC-00043',
        explicativa: 'chuva_bruta',
        melhor_defasagem_h: 1,
        r: 0.37,
        p_valor: 0.005,
        sinal_claro: true,
      },
      {
        ...base,
        ponto: 'DCSC-00037',
        explicativa: 'chuva_sem_local',
        melhor_defasagem_h: 1,
        r: 0.13,
        p_valor: 0.1,
        sinal_claro: false,
      },
    ])
    expect(await screen.findByText(/não encontramos relação clara/)).toBeInTheDocument()
    expect(screen.getByText(/não pôde ser confirmada nem descartada/)).toBeInTheDocument()
    expect(screen.getByText(/cerca de/)).toHaveTextContent('1 hora')
  })
})
