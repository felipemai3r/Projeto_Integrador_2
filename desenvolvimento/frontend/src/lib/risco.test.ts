import { describe, expect, it } from 'vitest'
import { SELOS, seloDe } from './risco'

describe('seloDe', () => {
  it('usa a faixa quando o dado esta ok', () => {
    expect(seloDe({ estado: 'ok', faixa: 'atencao' })).toBe('atencao')
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
