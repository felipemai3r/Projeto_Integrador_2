import { describe, expect, it } from 'vitest'
import {
  descreverTendencia,
  formatarDataHora,
  formatarHora,
  formatarMm,
  formatarNivel,
  formatarPercentual,
  nomeDaFonte,
  rotuloFonte,
  tempoRelativo,
} from './formato'

describe('formatarNivel e formatarMm', () => {
  it('usa virgula, duas casas e ponto de milhar em pt-BR', () => {
    expect(formatarNivel(0)).toBe('0,00')
    expect(formatarNivel(1234.5)).toBe('1.234,50')
    expect(formatarMm(0.4)).toBe('0,40')
    expect(formatarMm(248.28)).toBe('248,28')
  })

  it('arredonda para duas casas', () => {
    expect(formatarNivel(2.006)).toBe('2,01')
    expect(formatarNivel(2.004)).toBe('2,00')
  })

  it('mantem o sinal de valores negativos', () => {
    expect(formatarNivel(-0.5)).toBe('-0,50')
  })
})

describe('formatarPercentual', () => {
  it('nao mostra casas decimais', () => {
    expect(formatarPercentual(99.6)).toBe('100')
    expect(formatarPercentual(0)).toBe('0')
    expect(formatarPercentual(42.4)).toBe('42')
  })
})

describe('formatarHora e formatarDataHora', () => {
  it('convertem de UTC para o horario de Brasilia, qualquer que seja o fuso da maquina', () => {
    expect(formatarHora('2026-11-05T15:30:00Z')).toBe('12:30')
    expect(formatarHora('2026-11-05T02:05:00Z')).toBe('23:05') // virou o dia anterior
  })

  it('mostram dia e mes antes da hora', () => {
    expect(formatarDataHora('2026-11-05T15:30:00Z')).toMatch(/^05\/11,? 12:30$/)
    expect(formatarDataHora('2026-01-01T02:00:00Z')).toMatch(/^31\/12,? 23:00$/)
  })

  it('aceitam instante com outro deslocamento', () => {
    expect(formatarHora('2026-11-05T12:30:00-03:00')).toBe('12:30')
  })
})

describe('tempoRelativo', () => {
  const agora = new Date('2026-11-05T12:00:00Z')
  const antes = (ms: number) => new Date(agora.getTime() - ms).toISOString()
  const MIN = 60_000
  const H = 60 * MIN

  it('menos de meio minuto e "agora ha pouco"', () => {
    expect(tempoRelativo(antes(0), agora)).toBe('agora há pouco')
    expect(tempoRelativo(antes(29_000), agora)).toBe('agora há pouco')
  })

  it('a partir de meio minuto arredonda para 1 min', () => {
    expect(tempoRelativo(antes(30_000), agora)).toBe('há 1 min')
  })

  it('instante no futuro (relogio adiantado) nao vira tempo negativo', () => {
    expect(tempoRelativo(new Date(agora.getTime() + 10 * MIN).toISOString(), agora)).toBe(
      'agora há pouco',
    )
  })

  it('59 minutos ainda e em minutos e 60 vira horas', () => {
    expect(tempoRelativo(antes(59 * MIN), agora)).toBe('há 59 min')
    expect(tempoRelativo(antes(60 * MIN), agora)).toBe('há 1 h')
  })

  it('arredonda horas para o inteiro mais proximo', () => {
    expect(tempoRelativo(antes(90 * MIN), agora)).toBe('há 2 h')
    expect(tempoRelativo(antes(47 * H), agora)).toBe('há 47 h')
  })

  it('a partir de 48 horas passa a contar em dias', () => {
    expect(tempoRelativo(antes(48 * H), agora)).toBe('há 2 dias')
    expect(tempoRelativo(antes(72 * H), agora)).toBe('há 3 dias')
    expect(tempoRelativo(antes(1000 * 24 * H), agora)).toBe('há 1.000 dias')
  })
})

describe('descreverTendencia', () => {
  it('estavel nao traz numero, mesmo com taxa pequena negativa', () => {
    expect(descreverTendencia('estavel', -1.2, 0)).toBe('Estável')
    expect(descreverTendencia('estavel', 0, null)).toBe('Estável')
  })

  it('subindo usa o modulo da taxa e descendo tambem', () => {
    expect(descreverTendencia('subindo', 7.6, 0)).toBe('Subindo 8 cm por hora')
    expect(descreverTendencia('descendo', -7.6, 0)).toBe('Descendo 8 cm por hora')
  })

  it('"acelerando" vale a partir de 2 cm/h2 e so para quem sobe', () => {
    expect(descreverTendencia('subindo', 10, 2)).toBe('Subindo 10 cm por hora e acelerando')
    expect(descreverTendencia('subindo', 10, 1.9)).toBe('Subindo 10 cm por hora')
    expect(descreverTendencia('subindo', 10, null)).toBe('Subindo 10 cm por hora')
    expect(descreverTendencia('subindo', 10, undefined)).toBe('Subindo 10 cm por hora')
    expect(descreverTendencia('descendo', -10, 50)).toBe('Descendo 10 cm por hora')
  })

  it('tendencia vazia ou taxa ausente nao inventa texto', () => {
    expect(descreverTendencia('', 5, 0)).toBeNull()
    expect(descreverTendencia(undefined, 5, 0)).toBeNull()
    expect(descreverTendencia('subindo', undefined, 0)).toBeNull()
  })

  it('taxa zero e um valor valido (nao e tratada como ausente)', () => {
    expect(descreverTendencia('estavel', 0, 0)).toBe('Estável')
  })
})

describe('nomeDaFonte e rotuloFonte', () => {
  it('fontes estaduais viram "Defesa Civil de SC"', () => {
    for (const f of ['dcsc_graphql', 'dcsc_rest', 'dcsc_barragens']) {
      expect(nomeDaFonte(f)).toBe('Defesa Civil de SC')
    }
  })

  // O nivel do Revolver (DCSC-00174) vem de pdc_municipal: o selo nao pode mostrar o codigo.
  it('traduz a fonte do painel municipal em texto legivel', () => {
    const nome = nomeDaFonte('pdc_municipal')
    expect(nome).not.toContain('_')
    expect(nome).toBe('Defesa Civil de Presidente Getúlio')
  })

  it('remove o prefixo tecnico do nome da fonte so no inicio', () => {
    expect(rotuloFonte('Defesa Civil SC, GraphQL Qualle')).toBe('GraphQL Qualle')
    expect(rotuloFonte('Open-Meteo, previsao')).toBe('Open-Meteo, previsao')
    expect(rotuloFonte('Fonte da Defesa Civil SC, x')).toBe('Fonte da Defesa Civil SC, x')
  })

  it('o nome da fonte do painel municipal (sem o prefixo estadual) passa inteiro', () => {
    const nome = 'Defesa Civil de Presidente Getúlio, API do painel'
    expect(rotuloFonte(nome)).toBe(nome)
  })
})
