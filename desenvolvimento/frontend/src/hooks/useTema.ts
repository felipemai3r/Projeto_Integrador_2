import { useCallback, useEffect, useState } from 'react'

type Tema = 'light' | 'dark'
const CHAVE = 'fa-tema'

function lerPreferencia(): Tema | null {
  try {
    const v = localStorage.getItem(CHAVE)
    return v === 'light' || v === 'dark' ? v : null
  } catch {
    return null // armazenamento bloqueado: a pagina funciona sem lembrar a escolha
  }
}

/** Modo dia/noite. Sem escolha salva, segue a preferencia do sistema (via CSS). */
export function useTema() {
  const [tema, setTema] = useState<Tema | null>(lerPreferencia)

  useEffect(() => {
    const raiz = document.documentElement
    if (tema) raiz.dataset.theme = tema
    else delete raiz.dataset.theme
  }, [tema])

  const alternar = useCallback(() => {
    const sistemaNoite = window.matchMedia('(prefers-color-scheme: dark)').matches
    const atual = tema ?? (sistemaNoite ? 'dark' : 'light')
    const proximo: Tema = atual === 'dark' ? 'light' : 'dark'
    setTema(proximo)
    try {
      localStorage.setItem(CHAVE, proximo)
    } catch {
      /* sem persistencia */
    }
  }, [tema])

  return { tema, alternar }
}
