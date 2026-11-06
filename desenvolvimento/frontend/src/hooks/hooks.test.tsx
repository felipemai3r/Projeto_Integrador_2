import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessao } from './useSessao'
import { useTema } from './useTema'

const token = (expiraEm: string) => ({
  token: 'jwt',
  nome: 'Leo',
  papel: 'moderador',
  expira_em: expiraEm,
})

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  delete document.documentElement.dataset.theme
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('useSessao', () => {
  it('sem nada guardado nao ha sessao', () => {
    expect(renderHook(() => useSessao()).result.current.sessao).toBeNull()
  })

  it('retoma a sessao guardada que ainda nao venceu', () => {
    vi.useFakeTimers({ now: new Date('2026-11-05T12:00:00Z') })
    sessionStorage.setItem('fa-sessao', JSON.stringify(token('2026-11-05T12:00:01Z')))
    expect(renderHook(() => useSessao()).result.current.sessao?.nome).toBe('Leo')
  })

  it('sessao vencida ou no instante exato do vencimento e ignorada', () => {
    vi.useFakeTimers({ now: new Date('2026-11-05T12:00:00Z') })
    sessionStorage.setItem('fa-sessao', JSON.stringify(token('2026-11-05T12:00:00Z')))
    expect(renderHook(() => useSessao()).result.current.sessao).toBeNull()
  })

  it('conteudo corrompido no armazenamento e tratado como sem sessao', () => {
    sessionStorage.setItem('fa-sessao', '{quebrado')
    expect(renderHook(() => useSessao()).result.current.sessao).toBeNull()
  })

  it('entrar chama o login, guarda so na aba e passa a ter sessao', async () => {
    const t = token('2099-01-01T00:00:00Z')
    const fetchFalso = vi.fn(async () => new Response(JSON.stringify(t), { status: 200 }))
    vi.stubGlobal('fetch', fetchFalso)
    const { result } = renderHook(() => useSessao())
    await act(() => result.current.entrar('leo@exemplo.br', 'senha'))
    expect(result.current.sessao).toEqual(t)
    expect(JSON.parse(sessionStorage.getItem('fa-sessao') ?? '{}')).toEqual(t)
    expect(localStorage.getItem('fa-sessao')).toBeNull() // nunca persiste alem da aba
  })

  it('login recusado nao cria sessao e propaga o erro para a tela', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: 'Credenciais inválidas.' }), { status: 401 }),
      ),
    )
    const { result } = renderHook(() => useSessao())
    await expect(act(() => result.current.entrar('a', 'b'))).rejects.toMatchObject({ status: 401 })
    expect(result.current.sessao).toBeNull()
    expect(sessionStorage.getItem('fa-sessao')).toBeNull()
  })

  it('entrar funciona mesmo sem armazenamento disponivel', async () => {
    const t = token('2099-01-01T00:00:00Z')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(t), { status: 200 })),
    )
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    const { result } = renderHook(() => useSessao())
    await act(() => result.current.entrar('a', 'b'))
    expect(result.current.sessao).toEqual(t)
  })

  it('sair apaga a sessao do estado e do armazenamento', async () => {
    sessionStorage.setItem('fa-sessao', JSON.stringify(token('2099-01-01T00:00:00Z')))
    const { result } = renderHook(() => useSessao())
    expect(result.current.sessao).not.toBeNull()
    act(() => result.current.sair())
    expect(result.current.sessao).toBeNull()
    expect(sessionStorage.getItem('fa-sessao')).toBeNull()
  })
})

describe('useTema', () => {
  function sistema(escuro: boolean) {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: escuro && q.includes('dark') }))
  }

  it('sem escolha salva nao fixa tema e deixa o CSS seguir o sistema', () => {
    sistema(true)
    const { result } = renderHook(() => useTema())
    expect(result.current.tema).toBeNull()
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })

  it('aplica a escolha salva na raiz do documento', () => {
    localStorage.setItem('fa-tema', 'dark')
    sistema(false)
    const { result } = renderHook(() => useTema())
    expect(result.current.tema).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('valor salvo desconhecido e ignorado', () => {
    localStorage.setItem('fa-tema', 'sepia')
    sistema(false)
    expect(renderHook(() => useTema()).result.current.tema).toBeNull()
  })

  it('alternar sem escolha parte da preferencia do sistema e salva o oposto', () => {
    sistema(true) // sistema escuro: o primeiro clique vai para o claro
    const { result } = renderHook(() => useTema())
    act(() => result.current.alternar())
    expect(result.current.tema).toBe('light')
    expect(localStorage.getItem('fa-tema')).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('alternar duas vezes volta ao tema original', () => {
    sistema(false)
    const { result } = renderHook(() => useTema())
    act(() => result.current.alternar())
    act(() => result.current.alternar())
    expect(result.current.tema).toBe('light')
    expect(localStorage.getItem('fa-tema')).toBe('light')
  })

  it('alternar funciona mesmo sem permissao de gravar no armazenamento', () => {
    sistema(false)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    const { result } = renderHook(() => useTema())
    act(() => result.current.alternar())
    expect(result.current.tema).toBe('dark')
  })
})
