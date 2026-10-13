import { describe, expect, it } from 'vitest'
import { descreverTendencia, formatarNivel, tempoRelativo } from './formato'

describe('formato', () => {
  it('usa virgula decimal e duas casas no nivel', () => {
    expect(formatarNivel(4.6)).toBe('4,60')
    expect(formatarNivel(1.756)).toBe('1,76')
  })

  it('descreve a tendencia com numero e sentido', () => {
    expect(descreverTendencia('subindo', 12.4, 0)).toBe('Subindo 12 cm por hora')
    expect(descreverTendencia('descendo', -3.2, 0)).toBe('Descendo 3 cm por hora')
    expect(descreverTendencia('estavel', 0.4, 0)).toBe('Estável')
  })

  it('acrescenta "acelerando" so quando esta subindo e acelerando', () => {
    expect(descreverTendencia('subindo', 12, 3)).toBe('Subindo 12 cm por hora e acelerando')
    expect(descreverTendencia('descendo', -12, 3)).toBe('Descendo 12 cm por hora')
  })

  it('nao inventa tendencia sem dado', () => {
    expect(descreverTendencia(null, null, null)).toBeNull()
    expect(descreverTendencia('subindo', null, null)).toBeNull()
  })

  it('escreve o tempo relativo em portugues', () => {
    const agora = new Date('2026-10-12T20:00:00Z')
    expect(tempoRelativo('2026-10-12T19:55:00Z', agora)).toBe('há 5 min')
    expect(tempoRelativo('2026-10-12T17:00:00Z', agora)).toBe('há 3 h')
    expect(tempoRelativo('2026-10-12T20:00:00Z', agora)).toBe('agora há pouco')
  })
})
