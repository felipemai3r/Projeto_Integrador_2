/**
 * Telas com as estacoes novas do painel municipal: tres de serra que so medem chuva
 * (DC-PEU-002/003/004, sem nivel, sem limiar) e o Ribeirao Revolver como segundo alvo.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RainAccumulatedTable } from '../components/RainAccumulatedTable'
import { SourceStamp } from '../components/SourceStamp'
import { StationCard } from '../components/StationCard'
import type { ChuvaEstacao, NivelAtual } from '../lib/api'
import { Painel } from './Painel'
import { Qualidade } from './Qualidade'

vi.mock('../components/SeriesChart', () => ({
  SeriesChart: ({ titulo }: { titulo: string }) => <h3>{titulo}</h3>,
}))

const limiaresVazios = { atencao: null, alerta: null, alerta_alto: null, extremo: null }

const pg = {
  codigo: 'DCSC-00043',
  nome: 'PCD Presidente Getúlio',
  curso_dagua: 'Rio dos Índios',
  papel: 'alvo',
  latitude: -27.04,
  longitude: -49.62,
  limiares: { atencao: 4, alerta: 4.5, alerta_alto: 5.5, extremo: null },
}
const revolver = {
  codigo: 'DCSC-00174',
  nome: 'PCD ZAS Creche',
  curso_dagua: 'Ribeirão Revólver',
  papel: 'alvo',
  latitude: -27.05,
  longitude: -49.61,
  limiares: { atencao: 2.5, alerta: 3, alerta_alto: 3.5, extremo: null },
}
const serra = (codigo: string, nome: string) => ({
  codigo,
  nome,
  curso_dagua: null,
  papel: 'influencia',
  latitude: -27.08,
  longitude: -49.7,
  limiares: limiaresVazios,
})
const SERRAS = [
  serra('DC-PEU-002', 'PCD Serra Mirador (Mirante das Antenas)'),
  serra('DC-PEU-003', 'PCD Serra dos Índios (Posto de Saúde)'),
  serra('DC-PEU-004', 'PCD Serra Vencida (Escola Serra Vencida)'),
]

const nivelAtual = (
  estacao: NivelAtual['estacao'],
  extra: Partial<NivelAtual> = {},
): NivelAtual => ({
  estacao,
  estado: 'ok',
  nivel_m: 1.2,
  faixa: 'normal',
  taxa_cm_h: 0,
  aceleracao_cm_h2: 0,
  tendencia: 'estavel',
  medido_em: '2026-11-05T15:00:00Z',
  fonte: 'dcsc_graphql',
  motivo: null,
  ...extra,
})

const chuvaSerra = (estacao: string, nome: string, extra: Partial<ChuvaEstacao> = {}) => ({
  estacao,
  nome,
  papel: 'influencia',
  estado: 'ok' as const,
  medido_em: '2026-11-05T15:00:00Z',
  fonte: 'dcsc_graphql',
  acumulado_mm: { '1h': 0.4, '3h': null, '6h': null },
  ...extra,
})

function api(rotas: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const corpo = rotas[url]
      if (corpo === undefined) return new Response('{}', { status: 404 })
      return new Response(JSON.stringify(corpo), { status: 200 })
    }),
  )
}

function renderizar(ui: React.ReactElement) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Painel com as estacoes novas', () => {
  const rotasBase = {
    '/api/estacoes': [pg, revolver, ...SERRAS],
    '/api/estacoes/DCSC-00043/atual': nivelAtual(pg, { nivel_m: 1.78 }),
    '/api/estacoes/DCSC-00174/atual': nivelAtual(revolver, {
      nivel_m: 0.81,
      fonte: 'dcsc_graphql',
    }),
  }

  it('mostra um cartao por rio (alvo) e nenhum cartao para as estacoes de serra', async () => {
    api({ ...rotasBase, '/api/chuva/acumulada': [] })
    renderizar(<Painel />)
    expect(await screen.findByRole('heading', { name: 'Rio dos Índios' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Ribeirão Revólver' })).toBeInTheDocument()
    expect(screen.getByText('1,78')).toBeInTheDocument()
    expect(screen.getByText('0,81')).toBeInTheDocument()
    expect(screen.queryByText(/Serra/)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /DC-PEU/ })).not.toBeInTheDocument()
  })

  it('lista as serras na tabela de chuva, com traco onde a fonte nao traz a janela', async () => {
    api({
      ...rotasBase,
      '/api/chuva/acumulada': SERRAS.map((s) => chuvaSerra(s.codigo, s.nome)),
    })
    renderizar(<Painel />)
    const tabela = await screen.findByRole('table', { name: /Chuva acumulada/ })
    const linhas = within(tabela).getAllByRole('row').slice(1)
    expect(linhas).toHaveLength(3)
    expect(
      within(tabela).getByRole('rowheader', { name: 'Serra Mirador (Mirante das Antenas)' }),
    ).toBeInTheDocument()
    const primeira = within(linhas[0]!).getAllByRole('cell')
    expect(primeira[0]).toHaveTextContent('0,40') // 1h
    expect(primeira[1]).toHaveTextContent('—') // 3h sem valor
    expect(primeira.at(-1)).toHaveTextContent(/^\d{2}:\d{2}$/) // hora da leitura
  })

  it('serra sem nenhuma leitura fica fora da tabela de chuva em vez de mostrar linha vazia', async () => {
    api({
      ...rotasBase,
      '/api/chuva/acumulada': [
        chuvaSerra('DC-PEU-002', 'PCD Serra Mirador (Mirante das Antenas)'),
        chuvaSerra('DC-PEU-004', 'PCD Serra Vencida (Escola Serra Vencida)', {
          estado: 'indisponivel',
          medido_em: null,
          fonte: null,
          acumulado_mm: {},
        }),
      ],
    })
    renderizar(<Painel />)
    const tabela = await screen.findByRole('table', { name: /Chuva acumulada/ })
    expect(within(tabela).getAllByRole('row')).toHaveLength(2) // cabecalho + 1
    expect(within(tabela).queryByText(/Serra Vencida/)).not.toBeInTheDocument()
  })

  it('serra desatualizada aparece com o aviso e sem inventar zero', async () => {
    api({
      ...rotasBase,
      '/api/chuva/acumulada': [
        chuvaSerra('DC-PEU-003', 'PCD Serra dos Índios (Posto de Saúde)', {
          estado: 'desatualizado',
          acumulado_mm: { '1h': null },
        }),
      ],
    })
    renderizar(<Painel />)
    const linha = (await screen.findByRole('rowheader', { name: /Serra dos Índios/ })).closest(
      'tr',
    )!
    expect(within(linha).getByText('(desatualizado)')).toBeInTheDocument()
    expect(within(linha).queryByText('0,00')).not.toBeInTheDocument()
  })

  it('o Revolver (alvo) nao entra na tabela de chuva mesmo que a API o traga', async () => {
    api({
      ...rotasBase,
      '/api/chuva/acumulada': [
        chuvaSerra('DCSC-00174', 'PCD ZAS Creche', { papel: 'alvo' }),
        chuvaSerra('DC-PEU-002', 'PCD Serra Mirador (Mirante das Antenas)'),
      ],
    })
    renderizar(<Painel />)
    const tabela = await screen.findByRole('table', { name: /Chuva acumulada/ })
    expect(within(tabela).queryByText(/ZAS Creche/)).not.toBeInTheDocument()
    expect(within(tabela).getAllByRole('row')).toHaveLength(2)
  })

  it('alvo sem nivel agora (fonte fora do ar) mostra o motivo e continua na tela', async () => {
    api({
      ...rotasBase,
      '/api/estacoes/DCSC-00174/atual': nivelAtual(revolver, {
        estado: 'indisponivel',
        nivel_m: null,
        faixa: null,
        fonte: null,
        medido_em: null,
        motivo: 'Sem leitura desta estação no momento.',
      }),
      '/api/chuva/acumulada': [],
    })
    renderizar(<Painel />)
    expect(await screen.findByText('Sem leitura desta estação no momento.')).toBeInTheDocument()
    expect(screen.getByText('1,78')).toBeInTheDocument() // o outro rio nao e afetado
    expect(screen.getAllByText('Indisponível').length).toBeGreaterThan(0)
  })

  it('so estacoes de serra cadastradas (nenhum alvo) nao quebra a tela', async () => {
    api({ '/api/estacoes': SERRAS, '/api/chuva/acumulada': [] })
    renderizar(<Painel />)
    expect(await screen.findByRole('table', { name: /Chuva acumulada/ })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Como o nível variou' })).not.toBeInTheDocument()
  })
})

describe('StationCard do Revolver', () => {
  it('usa os limiares do Revolver para a faixa e mostra o nome do ribeirao', () => {
    render(
      <StationCard
        atual={nivelAtual(revolver, {
          nivel_m: 3.2,
          faixa: 'alerta',
          tendencia: 'subindo',
          taxa_cm_h: 8,
        })}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Ribeirão Revólver' })).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName(/Nível 3,20 metros, faixa alerta\./)
  })

  it('estacao sem curso d agua usa o nome da estacao como titulo', () => {
    const sem = { ...serra('DC-PEU-003', 'PCD Serra dos Índios (Posto de Saúde)') }
    render(
      <StationCard
        atual={nivelAtual(sem, {
          estado: 'indisponivel',
          nivel_m: null,
          faixa: null,
          fonte: null,
          medido_em: null,
          motivo: 'Esta estação não tem leitura de nível do rio.',
        })}
      />,
    )
    expect(
      screen.getByRole('heading', { name: 'PCD Serra dos Índios (Posto de Saúde)' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/não tem leitura de nível/)).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument() // sem regua
  })

  it('estacao com nivel mas sem nenhum limiar nao desenha a regua nem quebra', () => {
    const { container } = render(
      <StationCard atual={nivelAtual(serra('X', 'PCD X'), { nivel_m: 2 })} />,
    )
    expect(screen.getByText('2,00')).toBeInTheDocument()
    expect(container.querySelector('[role="img"]')).toBeNull()
  })

  it('SourceStamp nao aparece sem fonte ou sem horario', () => {
    const { container, rerender } = render(
      <SourceStamp fonte={null} estacao="X" medidoEm="2026-11-05T15:00:00Z" />,
    )
    expect(container).toBeEmptyDOMElement()
    rerender(<SourceStamp fonte="dcsc_graphql" estacao="X" medidoEm={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  // O nivel do Revolver vem de pdc_municipal: o selo mostra o nome da fonte, nao o codigo.
  it('selo de fonte do painel municipal mostra texto legivel e nao o codigo tecnico', () => {
    render(
      <SourceStamp fonte="pdc_municipal" estacao="DCSC-00174" medidoEm="2026-11-05T15:00:00Z" />,
    )
    expect(screen.queryByText(/pdc_municipal/)).not.toBeInTheDocument()
    expect(screen.getByText(/Defesa Civil de Presidente Getúlio/)).toBeInTheDocument()
  })
})

describe('RainAccumulatedTable com serras', () => {
  it('tira so o prefixo PCD/SDC-SC e preserva o parentese do nome da serra', () => {
    render(
      <RainAccumulatedTable
        estacoes={[
          chuvaSerra('DC-PEU-002', 'PCD Serra Mirador (Mirante das Antenas)'),
          chuvaSerra('DCSC-00037', 'SDC-SC Dona Emma'),
        ]}
      />,
    )
    expect(
      screen.getByRole('rowheader', { name: 'Serra Mirador (Mirante das Antenas)' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('rowheader', { name: 'Dona Emma' })).toBeInTheDocument()
  })

  it('janela com valor zero mostra 0,00 e nao traco (zero medido e dado)', () => {
    render(
      <RainAccumulatedTable
        estacoes={[chuvaSerra('DC-PEU-004', 'PCD Serra Vencida', { acumulado_mm: { '1h': 0 } })]}
      />,
    )
    const linha = screen.getByRole('rowheader', { name: 'Serra Vencida' }).closest('tr')!
    expect(within(linha).getAllByText('0,00')).toHaveLength(1)
    expect(within(linha).getAllByText('—')).toHaveLength(6)
  })

  it('leitura sem horario mostra "sem dado"', () => {
    render(
      <RainAccumulatedTable estacoes={[chuvaSerra('DC-PEU-004', 'PCD X', { medido_em: null })]} />,
    )
    expect(screen.getByText('sem dado')).toBeInTheDocument()
  })

  it('lista vazia mostra so o cabecalho', () => {
    render(<RainAccumulatedTable estacoes={[]} />)
    expect(screen.getAllByRole('row')).toHaveLength(1)
  })
})

describe('Qualidade com estacoes de chuva apenas', () => {
  it('linha de chuva nao mostra estado de sensor travado e nome vem sem prefixo', async () => {
    api({
      '/api/qualidade': {
        fontes: [
          {
            codigo: 'pdc_municipal',
            nome: 'Defesa Civil de Presidente Getúlio, API do painel',
            ultima_coleta: '2026-11-05T15:00:00Z',
            ultimo_sucesso: '2026-11-05T15:00:00Z',
            status_ultima: 'sucesso',
            falhas_seguidas: 0,
            instavel: false,
            ultima_mensagem: null,
          },
          {
            codigo: 'ana_hidroweb',
            nome: 'ANA, HidroWebService',
            ultima_coleta: null,
            ultimo_sucesso: null,
            status_ultima: null,
            falhas_seguidas: 0,
            instavel: false,
            ultima_mensagem: null,
          },
        ],
        estacoes: [
          {
            estacao: 'DC-PEU-002',
            nome: 'PCD Serra Mirador (Mirante das Antenas)',
            variavel: 'chuva_acumulada_mm',
            ultima_leitura: '2026-11-05T15:00:00Z',
            cobertura_24h_pct: 99.6,
            lacunas_7d: 0,
            maior_lacuna_min: 0,
            possivelmente_travado: true,
            descartadas_7d: 0,
            suspeitas_7d: 0,
          },
        ],
      },
    })
    renderizar(<Qualidade />)
    const tabela = await screen.findByRole('table', { name: /Cobertura nas últimas 24 horas/ })
    const linha = within(tabela)
      .getByRole('rowheader', { name: 'Serra Mirador (Mirante das Antenas)' })
      .closest('tr')!
    expect(within(linha).getByText('Chuva')).toBeInTheDocument()
    expect(within(linha).getByText('100%')).toBeInTheDocument()
    expect(within(linha).queryByText('Possivelmente travado')).not.toBeInTheDocument() // so vale para nivel
    expect(screen.getByText('Ainda não usada')).toBeInTheDocument() // fonte sem coleta
    expect(screen.getByText('Funcionando')).toBeInTheDocument()
  })
})
