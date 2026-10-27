import { describe, expect, it } from 'vitest'
import { faixaDoNivel, FAIXAS, SELOS, seloDe } from './risco'

describe('seloDe', () => {
  it('usa a faixa quando o dado esta ok', () => {
    expect(seloDe({ estado: 'ok', faixa: 'atencao' })).toBe('atencao')
    expect(seloDe({ estado: 'ok', faixa: 'extremo' })).toBe('extremo')
  })

  it('faixa antiga ou desconhecida nao vira selo de risco', () => {
    expect(seloDe({ estado: 'ok', faixa: 'observacao' })).toBe('indisponivel')
  })

  it('dado desatualizado nunca parece normal', () => {
    expect(seloDe({ estado: 'desatualizado', faixa: 'normal' })).toBe('desatualizado')
  })

  it('sem leitura ou sem faixa, fica indisponivel', () => {
    expect(seloDe({ estado: 'indisponivel', faixa: null })).toBe('indisponivel')
    expect(seloDe({ estado: 'ok', faixa: null })).toBe('indisponivel')
  })

  it('toda faixa tem rotulo e icone (cor nunca sozinha)', () => {
    for (const selo of Object.values(SELOS)) {
      expect(selo.rotulo.length).toBeGreaterThan(0)
      expect(selo.Icone).toBeDefined()
    }
  })
})

describe('faixaDoNivel', () => {
  const lim = { atencao: 4, alerta: 4.5, alerta_alto: 5.5 }

  it('classifica pelo limiar atingido (>=)', () => {
    expect(faixaDoNivel(3.99, lim)).toBe('normal')
    expect(faixaDoNivel(4, lim)).toBe('atencao')
    expect(faixaDoNivel(5, lim)).toBe('alerta')
    expect(faixaDoNivel(5.5, lim)).toBe('alerta_alto')
  })

  it('nunca classifica como extremo sem cota cadastrada', () => {
    expect(faixaDoNivel(99, lim)).toBe('alerta_alto')
    expect(faixaDoNivel(99, { ...lim, extremo: null })).toBe('alerta_alto')
    expect(faixaDoNivel(7, { ...lim, extremo: 7 })).toBe('extremo')
  })

  it('a escala tem cinco faixas, da menos para a mais grave', () => {
    expect(FAIXAS).toEqual(['normal', 'atencao', 'alerta', 'alerta_alto', 'extremo'])
  })
})
