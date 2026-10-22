const CHAVE_ID = 'farol-dispositivo'
const CHAVE_REACOES = 'farol-reacoes'

function ler(chave: string): string | null {
  try {
    return localStorage.getItem(chave)
  } catch {
    return null
  }
}

function gravar(chave: string, valor: string): void {
  try {
    localStorage.setItem(chave, valor)
  } catch {
    /* navegador sem armazenamento: a reacao vale so nesta visita */
  }
}

/** Identificador anonimo deste navegador. So o hash dele chega ao banco (RN06). */
export function idDoDispositivo(): string {
  let id = ler(CHAVE_ID)
  if (!id) {
    id = crypto.randomUUID()
    gravar(CHAVE_ID, id)
  }
  return id
}

export type TipoReacao = 'curtida' | 'denuncia'

function minhas(): Record<string, true> {
  try {
    return JSON.parse(ler(CHAVE_REACOES) ?? '{}') as Record<string, true>
  } catch {
    return {}
  }
}

/** O que este aparelho ja fez, para mostrar o botao marcado. */
export const jaReagi = (id: number, tipo: TipoReacao): boolean => Boolean(minhas()[`${id}:${tipo}`])

export function marcarReacao(id: number, tipo: TipoReacao, ativa: boolean): void {
  const m = minhas()
  if (ativa) m[`${id}:${tipo}`] = true
  else delete m[`${id}:${tipo}`]
  gravar(CHAVE_REACOES, JSON.stringify(m))
}
