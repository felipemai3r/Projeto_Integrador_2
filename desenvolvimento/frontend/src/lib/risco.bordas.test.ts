import { describe, expect, it } from 'vitest'
import { ehFaixa, faixaDoNivel, FAIXAS, nomeDaFaixa, SELOS, seloDe } from './risco'

describe('ehFaixa', () => {
  it('aceita as cinco faixas e recusa o resto', () => {
    for (const f of FAIXAS) expect(ehFaixa(f)).toBe(true)
    for (const x of ['', 'normal ', 'Normal', 'observacao', 'desatualizado', null, undefined]) {
      expect(ehFaixa(x)).toBe(false)
    }
  })

  it('selos de dado (desatualizado, indisponivel) nao sao faixas de risco', () => {
    expect(ehFaixa('indisponivel')).toBe(false)
  })
})

describe('FAIXAS e SELOS', () => {
  it('toda faixa tem selo e os dois selos de estado do dado existem', () => {
    for (const f of FAIXAS) expect(SELOS[f]).toBeDefined()
    expect(SELOS.desatualizado.rotulo).toBe('Dado desatualizado')
    expect(SELOS.indisponivel.rotulo).toBe('Indisponível')
  })

  it('rotulos e frases nao se repetem (a cor nunca e a unica diferenca)', () => {
    const rotulos = Object.values(SELOS).map((s) => s.rotulo)
    const icones = Object.values(SELOS).map((s) => s.Icone)
    expect(new Set(rotulos).size).toBe(rotulos.length)
    expect(new Set(icones).size).toBe(icones.length) // cada faixa tem formato de icone proprio
  })

  it('escala da Defesa Civil de SC: nomes das faixas', () => {
    expect(SELOS.normal.rotulo).toBe('Normal')
    expect(SELOS.atencao.rotulo).toBe('Atenção')
    expect(SELOS.alerta.rotulo).toBe('Alerta')
    expect(SELOS.alerta_alto.rotulo).toBe('Alerta alto')
    expect(SELOS.extremo.rotulo).toBe('Aja imediatamente')
  })
})

describe('nomeDaFaixa', () => {
  it('devolve o texto para usar no meio da frase', () => {
    expect(nomeDaFaixa('alerta_alto')).toBe('alerta alto')
    expect(nomeDaFaixa('extremo')).toBe('risco extremo')
    expect(nomeDaFaixa('atencao')).toBe('atenção')
  })

  it('valor desconhecido passa como veio', () => {
    expect(nomeDaFaixa('observacao')).toBe('observacao')
    expect(nomeDaFaixa('')).toBe('')
  })
})

describe('faixaDoNivel com limiares do Revolver', () => {
  const revolver = { atencao: 2.5, alerta: 3.0, alerta_alto: 3.5 }
  const indios = { atencao: 4.0, alerta: 4.5, alerta_alto: 5.5 }

  it('cada estacao usa os proprios limiares', () => {
    expect(faixaDoNivel(3.2, revolver)).toBe('alerta')
    expect(faixaDoNivel(3.2, indios)).toBe('normal')
  })

  it('limiar exato ja conta e logo abaixo nao', () => {
    expect(faixaDoNivel(2.5, revolver)).toBe('atencao')
    expect(faixaDoNivel(2.4999, revolver)).toBe('normal')
    expect(faixaDoNivel(3.5, revolver)).toBe('alerta_alto')
  })

  it('estacao sem limiares (as de serra) fica sempre normal', () => {
    expect(faixaDoNivel(10, {})).toBe('normal')
    expect(
      faixaDoNivel(10, { atencao: null, alerta: null, alerta_alto: null, extremo: null }),
    ).toBe('normal')
  })

  it('limiar zero e valido (nao e tratado como ausente)', () => {
    expect(faixaDoNivel(0, { atencao: 0 })).toBe('atencao')
  })

  it('nivel negativo e normal', () => {
    expect(faixaDoNivel(-1, revolver)).toBe('normal')
  })

  it('extremo so quando houver cota', () => {
    expect(faixaDoNivel(4.9, { ...revolver, extremo: 4.8 })).toBe('extremo')
    expect(faixaDoNivel(4.7, { ...revolver, extremo: 4.8 })).toBe('alerta_alto')
  })
})

describe('seloDe', () => {
  it('o estado do dado vence a faixa (indisponivel antes de desatualizado)', () => {
    expect(seloDe({ estado: 'indisponivel', faixa: 'alerta' })).toBe('indisponivel')
    expect(seloDe({ estado: 'desatualizado', faixa: 'extremo' })).toBe('desatualizado')
  })

  it('dado ok com cada faixa devolve a propria faixa', () => {
    for (const f of FAIXAS) expect(seloDe({ estado: 'ok', faixa: f })).toBe(f)
  })

  it('faixa ausente (undefined) com dado ok e indisponivel, nunca normal', () => {
    expect(seloDe({ estado: 'ok', faixa: undefined })).toBe('indisponivel')
  })
})
