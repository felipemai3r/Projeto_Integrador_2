import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { idDoDispositivo, jaReagi, marcarReacao } from './dispositivo'

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('idDoDispositivo', () => {
  it('cria um identificador na primeira vez e repete o mesmo depois', () => {
    const a = idDoDispositivo()
    expect(a).toMatch(/^[0-9a-f-]{36}$/)
    expect(idDoDispositivo()).toBe(a)
    expect(localStorage.getItem('farol-dispositivo')).toBe(a)
  })

  it('reaproveita o identificador ja guardado', () => {
    localStorage.setItem('farol-dispositivo', 'id-antigo')
    expect(idDoDispositivo()).toBe('id-antigo')
  })

  it('sem armazenamento disponivel gera um id e nao quebra', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    expect(idDoDispositivo()).toMatch(/^[0-9a-f-]{36}$/)
  })
})

describe('reacoes deste aparelho', () => {
  it('comeca sem nenhuma reacao', () => {
    expect(jaReagi(1, 'curtida')).toBe(false)
    expect(jaReagi(1, 'denuncia')).toBe(false)
  })

  it('marcar e desmarcar uma curtida', () => {
    marcarReacao(7, 'curtida', true)
    expect(jaReagi(7, 'curtida')).toBe(true)
    marcarReacao(7, 'curtida', false)
    expect(jaReagi(7, 'curtida')).toBe(false)
  })

  it('curtida e denuncia da mesma ocorrencia sao independentes', () => {
    marcarReacao(7, 'curtida', true)
    expect(jaReagi(7, 'denuncia')).toBe(false)
    marcarReacao(7, 'denuncia', true)
    marcarReacao(7, 'curtida', false)
    expect(jaReagi(7, 'denuncia')).toBe(true)
  })

  it('ocorrencias diferentes nao se misturam (1 nao e 11)', () => {
    marcarReacao(1, 'curtida', true)
    expect(jaReagi(11, 'curtida')).toBe(false)
    expect(jaReagi(1, 'curtida')).toBe(true)
  })

  it('desfazer o que nunca foi marcado nao quebra', () => {
    expect(() => marcarReacao(99, 'denuncia', false)).not.toThrow()
    expect(jaReagi(99, 'denuncia')).toBe(false)
  })

  it('armazenamento corrompido e tratado como vazio e volta a funcionar', () => {
    localStorage.setItem('farol-reacoes', '{nao e json')
    expect(jaReagi(1, 'curtida')).toBe(false)
    marcarReacao(1, 'curtida', true)
    expect(jaReagi(1, 'curtida')).toBe(true)
  })

  it('nao guarda nada alem do par ocorrencia:tipo (sem dado pessoal)', () => {
    marcarReacao(5, 'denuncia', true)
    expect(JSON.parse(localStorage.getItem('farol-reacoes') ?? '{}')).toEqual({
      '5:denuncia': true,
    })
  })

  it('sem armazenamento a reacao vale so na visita e nao levanta erro', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('cheio')
    })
    expect(() => marcarReacao(3, 'curtida', true)).not.toThrow()
  })
})
