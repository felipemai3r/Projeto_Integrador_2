import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PrevisaoHorizonte, PrevisaoOut } from '../lib/api'
import { ChuvaEstimadaNotice } from './ChuvaEstimadaNotice'
import { PrevisaoTabela } from './PrevisaoTabela'

const horizonte = (h: number, extra: Partial<PrevisaoHorizonte> = {}): PrevisaoHorizonte => ({
  horizonte_h: h,
  disponivel: false,
  motivo: null,
  valido_para: null,
  nivel_m: null,
  incerteza_m: null,
  intervalo_m: null,
  faixa: null,
  modelo: null,
  extrapolacao: [],
  ...extra,
})

const previsao = (
  horizontes: PrevisaoHorizonte[],
  extra: Partial<PrevisaoOut> = {},
): PrevisaoOut => ({
  estacao: 'DCSC-00174',
  origem: 'operacional',
  base_em: '2026-11-05T15:00:00Z',
  nivel_base_m: 0.81,
  horizontes,
  chuva_estimada: [],
  aviso: 'Estimativa de apoio.',
  ...extra,
})

const disponivel = (h: number, extra: Partial<PrevisaoHorizonte> = {}) =>
  horizonte(h, {
    disponivel: true,
    nivel_m: 3.1,
    intervalo_m: [2.9, 3.3],
    incerteza_m: 0.2,
    faixa: 'alerta',
    valido_para: '2026-11-05T18:00:00Z',
    ...extra,
  })

describe('PrevisaoTabela', () => {
  it('horizonte disponivel mostra nivel, intervalo, horario e faixa como previsao', () => {
    render(<PrevisaoTabela previsao={previsao([disponivel(3)])} />)
    const item = screen.getByText('Daqui a 3 h').closest('li')!
    expect(within(item).getByText(/3,10/)).toBeInTheDocument()
    expect(within(item).getByText(/Entre 2,90 e 3,30 m \(95% de confiança\)/)).toBeInTheDocument()
    expect(within(item).getByText(/Alerta \(previsão\)/)).toBeInTheDocument()
    expect(within(item).getByText(/05\/11,? 15:00/)).toBeInTheDocument()
  })

  it('mostra o nivel de confianca que a API informa para o horizonte', () => {
    render(<PrevisaoTabela previsao={previsao([disponivel(24, { confianca: 0.8 })])} />)
    const item = screen.getByText('Daqui a 24 h').closest('li')!
    expect(within(item).getByText(/\(80% de confiança\)/)).toBeInTheDocument()
  })

  it('cenario hipotetico rotula a faixa como cenario e nao como previsao', () => {
    render(<PrevisaoTabela previsao={previsao([disponivel(3)], { origem: 'cenario' })} />)
    expect(screen.getByText(/Alerta \(cenário\)/)).toBeInTheDocument()
    expect(screen.queryByText(/\(previsão\)/)).not.toBeInTheDocument()
  })

  it('horizonte indisponivel mostra o motivo e nenhum numero', () => {
    render(
      <PrevisaoTabela
        previsao={previsao([horizonte(6, { motivo: 'Só há 20 dias de dados completos.' })])}
      />,
    )
    expect(screen.getByText(/Só há 20 dias/)).toBeInTheDocument()
    expect(screen.queryByText(/\d,\d\d/)).not.toBeInTheDocument()
  })

  it('indisponivel sem motivo usa o texto padrao', () => {
    render(<PrevisaoTabela previsao={previsao([horizonte(6)])} />)
    expect(screen.getByText(/Ainda não disponível\./)).toBeInTheDocument()
  })

  it('marcado como disponivel mas sem nivel nao inventa numero', () => {
    render(
      <PrevisaoTabela
        previsao={previsao([horizonte(6, { disponivel: true, motivo: 'Sem dados recentes.' })])}
      />,
    )
    expect(screen.getByText(/Sem dados recentes\./)).toBeInTheDocument()
  })

  it('previsao fora do que o modelo conhece traz o aviso de confianca baixa', () => {
    render(
      <PrevisaoTabela previsao={previsao([disponivel(3, { extrapolacao: ['chuva_local_1h'] })])} />,
    )
    expect(screen.getByRole('note')).toHaveTextContent(/confiança baixa/)
  })

  it('sem extrapolacao nao ha aviso de confianca baixa', () => {
    render(<PrevisaoTabela previsao={previsao([disponivel(3)])} />)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('faixa desconhecida da API nao vira selo', () => {
    render(<PrevisaoTabela previsao={previsao([disponivel(3, { faixa: 'observacao' })])} />)
    expect(screen.queryByText(/observacao/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\(previsão\)/)).not.toBeInTheDocument()
  })

  it('previsao sem faixa (estacao sem limiar) mostra o nivel sem selo', () => {
    render(<PrevisaoTabela previsao={previsao([disponivel(3, { faixa: null })])} />)
    expect(screen.getByText(/3,10/)).toBeInTheDocument()
    expect(screen.queryByText(/\(previsão\)/)).not.toBeInTheDocument()
  })

  it('mostra todos os horizontes na ordem recebida', () => {
    render(<PrevisaoTabela previsao={previsao([horizonte(1), horizonte(3), horizonte(24)])} />)
    const itens = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(itens[0]).toMatch(/Daqui a 1 h/)
    expect(itens[1]).toMatch(/Daqui a 3 h/)
    expect(itens[2]).toMatch(/Daqui a 24 h/)
  })

  it('mostra o aviso de chuva estimada quando houver', () => {
    render(
      <PrevisaoTabela
        previsao={previsao([disponivel(3)], {
          chuva_estimada: [{ codigo: 'DC-PEU-004', nome: 'PCD Serra Vencida', horas: 5 }],
        })}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent(
      'Sem leitura de chuva em Serra Vencida por 5 h.',
    )
  })
})

describe('ChuvaEstimadaNotice', () => {
  it('sem pontos nao renderiza nada', () => {
    const { container } = render(<ChuvaEstimadaNotice pontos={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('um aviso por ponto e uma explicacao unica de que usou a media', () => {
    render(
      <ChuvaEstimadaNotice
        pontos={[
          { codigo: 'A', nome: 'PCD Serra Mirador', horas: 3 },
          { codigo: 'B', nome: 'Witmarsum', horas: 14 },
        ]}
      />,
    )
    expect(screen.getByText('Sem leitura de chuva em Serra Mirador por 3 h.')).toBeInTheDocument()
    expect(screen.getByText('Sem leitura de chuva em Witmarsum por 14 h.')).toBeInTheDocument()
    expect(screen.getAllByText(/usamos a média dos outros pontos/)).toHaveLength(1)
  })
})
