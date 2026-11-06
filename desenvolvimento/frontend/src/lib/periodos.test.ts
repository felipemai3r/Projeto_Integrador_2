import { describe, expect, it } from 'vitest'
import { descreverPeriodo, PERIODO_PADRAO, PERIODOS } from './periodos'

describe('PERIODOS', () => {
  it('estao em ordem crescente, sem repeticao e ate 720 h (maximo da API de series)', () => {
    const valores = PERIODOS.map((p) => p.valor)
    expect(valores).toEqual([...valores].sort((a, b) => a - b))
    expect(new Set(valores).size).toBe(valores.length)
    expect(Math.max(...valores)).toBe(720)
  })

  it('o periodo padrao esta entre as opcoes', () => {
    expect(PERIODOS.map((p) => p.valor)).toContain(PERIODO_PADRAO)
  })

  it('todo periodo tem rotulo nao vazio', () => {
    for (const p of PERIODOS) expect(p.rotulo.length).toBeGreaterThan(0)
  })
})

describe('descreverPeriodo', () => {
  it('uma hora e singular', () => {
    expect(descreverPeriodo(1)).toBe('última hora')
  })

  it('ate 24 h concorda no feminino e a partir de 3 dias no masculino', () => {
    expect(descreverPeriodo(6)).toBe('últimas 6 horas')
    expect(descreverPeriodo(24)).toBe('últimas 24 horas')
    expect(descreverPeriodo(72)).toBe('últimos 3 dias')
    expect(descreverPeriodo(168)).toBe('últimos 7 dias')
    expect(descreverPeriodo(720)).toBe('últimos 30 dias')
  })

  it('periodo curto fora da lista cai em horas', () => {
    expect(descreverPeriodo(12)).toBe('últimas 12 horas')
  })
})
