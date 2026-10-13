import { useCallback, useState } from 'react'
import { api, type TokenOut } from '../lib/api'

const CHAVE = 'fa-sessao'

function ler(): TokenOut | null {
  try {
    const bruto = sessionStorage.getItem(CHAVE)
    if (!bruto) return null
    const t = JSON.parse(bruto) as TokenOut
    return new Date(t.expira_em) > new Date() ? t : null
  } catch {
    return null
  }
}

/** Sessao de quem modera. Fica so na aba (sessionStorage) e some ao fechar. */
export function useSessao() {
  const [sessao, setSessao] = useState<TokenOut | null>(ler)

  const entrar = useCallback(async (email: string, senha: string) => {
    const t = await api.login(email, senha)
    try {
      sessionStorage.setItem(CHAVE, JSON.stringify(t))
    } catch {
      /* sem persistencia: a sessao vale ate recarregar */
    }
    setSessao(t)
  }, [])

  const sair = useCallback(() => {
    try {
      sessionStorage.removeItem(CHAVE)
    } catch {
      /* nada a limpar */
    }
    setSessao(null)
  }, [])

  return { sessao, entrar, sair }
}
