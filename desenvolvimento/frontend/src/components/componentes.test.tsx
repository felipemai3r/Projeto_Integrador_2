import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { NivelAtual } from '../lib/api'
import { AlertBanner } from './AlertBanner'
import { LevelGauge } from './LevelGauge'
import { RainAccumulatedTable } from './RainAccumulatedTable'
import { RiskBadge } from './RiskBadge'
import { StationCard } from './StationCard'

const estacao = {
  codigo: 'DCSC-00043',
  nome: 'PCD Presidente Getúlio',
  curso_dagua: 'Rio dos Índios',
  papel: 'alvo',
  latitude: -27.04,
  longitude: -49.62,
  limiares: { observacao: 4, atencao: 4.5, alerta: 5.5 },
}

const base: NivelAtual = {
  estacao,
  estado: 'ok',
  nivel_m: 4.62,
  faixa: 'atencao',
  taxa_cm_h: 12,
  aceleracao_cm_h2: 1,
  tendencia: 'subindo',
  medido_em: '2026-10-12T17:35:00Z',
  fonte: 'dcsc_graphql',
  motivo: null,
}

describe('RiskBadge', () => {
  it('mostra o rotulo em texto, nao so a cor', () => {
    render(<RiskBadge faixa="alerta" />)
    expect(screen.getByText('Alerta')).toBeInTheDocument()
  })

  it('rotula a origem quando e previsao', () => {
    render(<RiskBadge faixa="atencao" origem="previsto" />)
    expect(screen.getByText(/Atenção \(previsão\)/)).toBeInTheDocument()
  })
})

describe('StationCard', () => {
  it('mostra nivel, faixa, tendencia e fonte com horario', () => {
    render(<StationCard atual={base} />)
    expect(screen.getByRole('heading', { name: 'Rio dos Índios' })).toBeInTheDocument()
    expect(screen.getByText('4,62')).toBeInTheDocument()
    expect(screen.getByText('Atenção')).toBeInTheDocument()
    expect(screen.getByText('Subindo 12 cm por hora')).toBeInTheDocument()
    expect(screen.getByText(/Fonte: Defesa Civil de SC · DCSC-00043/)).toBeInTheDocument()
  })

  it('dado desatualizado mostra o aviso e o selo cinza, mantendo o ultimo valor', () => {
    render(<StationCard atual={{ ...base, estado: 'desatualizado' }} />)
    expect(screen.getByRole('status')).toHaveTextContent(/Dado desatualizado/)
    expect(screen.getByText('Dado desatualizado', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('4,62')).toBeInTheDocument()
    expect(screen.queryByText('Subindo 12 cm por hora')).not.toBeInTheDocument()
  })

  it('estacao sem leitura fica indisponivel, sem inventar numero', () => {
    render(
      <StationCard
        atual={{
          ...base,
          estado: 'indisponivel',
          nivel_m: null,
          faixa: null,
          fonte: null,
          medido_em: null,
          motivo: 'Esta estação não tem leitura de nível do rio.',
        }}
      />,
    )
    expect(screen.getByText('Indisponível')).toBeInTheDocument()
    expect(screen.getByText(/não tem leitura de nível/)).toBeInTheDocument()
    expect(screen.queryByText(/\d,\d\d/)).not.toBeInTheDocument()
  })
})

describe('LevelGauge', () => {
  it('descreve o nivel e os limiares para leitor de tela', () => {
    render(<LevelGauge nivelM={4.62} limiares={estacao.limiares} />)
    const regua = screen.getByRole('img')
    expect(regua).toHaveAccessibleName(/Nível 4,62 metros, faixa atenção/)
  })

  it('nao desenha nada sem limiares', () => {
    const { container } = render(<LevelGauge nivelM={2} limiares={{}} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('RainAccumulatedTable', () => {
  it('mostra traco para janela sem valor e aponta dado desatualizado', () => {
    render(
      <RainAccumulatedTable
        estacoes={[
          {
            estacao: 'DCSC-00037',
            nome: 'SDC-SC Dona Emma',
            papel: 'influencia',
            estado: 'desatualizado',
            medido_em: '2026-10-12T17:00:00Z',
            fonte: 'dcsc_graphql',
            acumulado_mm: { '1h': 1.3, '24h': 1.5, '72h': 6.9 },
          },
        ]}
      />,
    )
    expect(screen.getByRole('rowheader', { name: /Dona Emma/ })).toHaveTextContent(
      '(desatualizado)',
    )
    expect(screen.getByText('1,3')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})

const alerta = {
  id: 1,
  estacao: 'DCSC-00043',
  nome: 'PCD Presidente Getúlio',
  curso_dagua: 'Rio dos Índios',
  faixa_anterior: 'normal',
  faixa_nova: 'atencao',
  sobe: true,
  origem: 'observado',
  criado_em: '2026-10-12T17:00:00Z',
  encerrado_em: null,
  vigente: true,
  nivel_m: 4.62,
  aviso: 'Estimativa de apoio.',
}

describe('AlertBanner', () => {
  it('mostra o alerta mais grave com nivel, origem e fonte oficial', () => {
    render(<AlertBanner alertas={[alerta, { ...alerta, id: 2, faixa_nova: 'alerta' }]} />)
    expect(screen.getByText('Rio dos Índios em alerta')).toBeInTheDocument()
    expect(screen.getByText(/Nível 4,62 m\. Observado\./)).toBeInTheDocument()
    expect(screen.getByText(/Mais 1 alerta vigente/)).toBeInTheDocument()
    expect(screen.getByText(/Fonte oficial: Defesa Civil/)).toBeInTheDocument()
  })

  it('rotula previsao como previsao, nao como observado', () => {
    render(<AlertBanner alertas={[{ ...alerta, origem: 'previsto' }]} />)
    expect(screen.getByText(/Previsão\./)).toBeInTheDocument()
  })

  it('nao mostra nada sem alerta vigente', () => {
    const { container } = render(<AlertBanner alertas={[{ ...alerta, vigente: false }]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('so a observacao pode ser dispensada; atencao permanece', async () => {
    const { rerender } = render(<AlertBanner alertas={[{ ...alerta, faixa_nova: 'observacao' }]} />)
    await userEvent.click(screen.getByRole('button', { name: 'Dispensar' }))
    expect(screen.queryByText(/em observação/)).not.toBeInTheDocument()
    rerender(<AlertBanner alertas={[{ ...alerta, id: 3 }]} />)
    expect(screen.queryByRole('button', { name: 'Dispensar' })).not.toBeInTheDocument()
    expect(screen.getByText('Rio dos Índios em atenção')).toBeInTheDocument()
  })
})
