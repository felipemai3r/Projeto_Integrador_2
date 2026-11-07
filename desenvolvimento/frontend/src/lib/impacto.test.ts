import { describe, expect, it } from 'vitest'
import {
  categoriaDoTipo,
  ehGravidade,
  exigeGravidade,
  GRAVIDADES,
  IMPACTOS,
  rotuloDoImpacto,
  tiposDaCategoria,
} from './impacto'

describe('rotuloDoImpacto', () => {
  it('traduz cada tipo conhecido', () => {
    expect(rotuloDoImpacto('via_intransitavel')).toBe('Rua ou estrada intransitável')
    expect(rotuloDoImpacto('agua_calcada')).toBe('Água na calçada')
    expect(rotuloDoImpacto('agua_imovel')).toBe('Água dentro de imóvel')
    expect(rotuloDoImpacto('deslizamento')).toBe('Deslizamento de terra ou barranco')
    expect(rotuloDoImpacto('queda_rocha')).toBe('Queda de pedras ou rochas')
    expect(rotuloDoImpacto('movimentacao_terra')).toBe('Sinais de movimentação de terra')
    expect(rotuloDoImpacto('outro')).toBe('Outro')
  })

  it('tipo desconhecido passa como veio, sem quebrar', () => {
    expect(rotuloDoImpacto('meteoro')).toBe('meteoro')
    expect(rotuloDoImpacto('')).toBe('')
  })

  it('todo tipo e toda gravidade têm rótulo e ícone (cor ou imagem nunca sozinhas)', () => {
    for (const { rotulo, Icone } of [...Object.values(IMPACTOS), ...Object.values(GRAVIDADES)]) {
      expect(rotulo.length).toBeGreaterThan(0)
      expect(Icone).toBeDefined()
    }
  })
})

describe('classificação', () => {
  it('separa alagamento de movimento de massa', () => {
    expect(tiposDaCategoria('alagamento')).toEqual([
      'via_intransitavel',
      'agua_calcada',
      'agua_imovel',
    ])
    expect(tiposDaCategoria('movimento_massa')).toEqual([
      'deslizamento',
      'queda_rocha',
      'movimentacao_terra',
    ])
    expect(categoriaDoTipo('meteoro')).toBe('outro')
  })

  it('só movimento de massa pede gravidade', () => {
    expect(exigeGravidade('deslizamento')).toBe(true)
    expect(exigeGravidade('movimentacao_terra')).toBe(true)
    expect(exigeGravidade('agua_imovel')).toBe(false)
    expect(exigeGravidade('outro')).toBe(false)
  })

  it('reconhece as gravidades válidas', () => {
    expect(ehGravidade('alta')).toBe(true)
    expect(ehGravidade('enorme')).toBe(false)
    expect(ehGravidade(null)).toBe(false)
  })
})
