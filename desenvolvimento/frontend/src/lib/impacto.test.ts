import { describe, expect, it } from 'vitest'
import { IMPACTOS, rotuloDoImpacto } from './impacto'

describe('rotuloDoImpacto', () => {
  it('traduz cada tipo conhecido', () => {
    expect(rotuloDoImpacto('via_intransitavel')).toBe('Rua ou estrada intransitável')
    expect(rotuloDoImpacto('agua_calcada')).toBe('Água na calçada')
    expect(rotuloDoImpacto('agua_imovel')).toBe('Água dentro de imóvel')
    expect(rotuloDoImpacto('outro')).toBe('Outro')
  })

  it('tipo desconhecido passa como veio, sem quebrar', () => {
    expect(rotuloDoImpacto('deslizamento')).toBe('deslizamento')
    expect(rotuloDoImpacto('')).toBe('')
  })

  it('todo tipo tem rotulo e icone (cor ou imagem nunca sozinhas)', () => {
    for (const { rotulo, Icone } of Object.values(IMPACTOS)) {
      expect(rotulo.length).toBeGreaterThan(0)
      expect(Icone).toBeDefined()
    }
  })
})
