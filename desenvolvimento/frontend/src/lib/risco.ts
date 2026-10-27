import {
  CircleAlert,
  CircleCheck,
  CircleOff,
  ClockAlert,
  OctagonAlert,
  Siren,
  TriangleAlert,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { NivelAtual } from './api'

/** Escala de risco da Defesa Civil de SC, da menos para a mais grave. */
export type Faixa = 'normal' | 'atencao' | 'alerta' | 'alerta_alto' | 'extremo'
export type SeloRisco = Faixa | 'desatualizado' | 'indisponivel'
export type Origem = 'observado' | 'previsto' | 'cenario'

/**
 * Cor nunca vai sozinha: toda faixa tem icone e rotulo (Farol, fundamento 02). Cada faixa tem um
 * formato de icone proprio (circulo, triangulo, octogono, sirene), para nao depender da cor.
 * `emFrase` entra em textos como "Rio X em alerta alto".
 */
export const SELOS: Record<SeloRisco, { rotulo: string; emFrase: string; Icone: LucideIcon }> = {
  normal: { rotulo: 'Normal', emFrase: 'normal', Icone: CircleCheck },
  atencao: { rotulo: 'Atenção', emFrase: 'atenção', Icone: CircleAlert },
  alerta: { rotulo: 'Alerta', emFrase: 'alerta', Icone: TriangleAlert },
  alerta_alto: { rotulo: 'Alerta alto', emFrase: 'alerta alto', Icone: OctagonAlert },
  extremo: { rotulo: 'Aja imediatamente', emFrase: 'risco extremo', Icone: Siren },
  desatualizado: { rotulo: 'Dado desatualizado', emFrase: 'dado desatualizado', Icone: ClockAlert },
  indisponivel: { rotulo: 'Indisponível', emFrase: 'indisponível', Icone: CircleOff },
}

/** Faixas de risco em ordem de gravidade (a mesma ordem do backend). */
export const FAIXAS: readonly Faixa[] = ['normal', 'atencao', 'alerta', 'alerta_alto', 'extremo']

export function ehFaixa(valor: string | null | undefined): valor is Faixa {
  return valor != null && (FAIXAS as readonly string[]).includes(valor)
}

/** Limiares por faixa (m). `extremo` ainda nao tem cota cadastrada e pode faltar. */
export type Limiares = {
  atencao?: number | null
  alerta?: number | null
  alerta_alto?: number | null
  extremo?: number | null
}

/** Nome da faixa para usar no meio de uma frase ("alerta alto"); valor desconhecido passa como veio. */
export function nomeDaFaixa(valor: string): string {
  return ehFaixa(valor) ? SELOS[valor].emFrase : valor
}

/** Faixa que o nivel atinge (>=). Faixa sem limiar (hoje, `extremo`) nunca e atingida. */
export function faixaDoNivel(nivelM: number, limiares: Limiares): Faixa {
  let faixa: Faixa = 'normal'
  for (const f of FAIXAS.slice(1)) {
    const limiar = limiares[f as keyof Limiares]
    if (limiar != null && nivelM >= limiar) faixa = f
  }
  return faixa
}

/** Dado velho ou ausente nunca pode parecer "normal": o estado do dado vence a faixa. */
export function seloDe(atual: Pick<NivelAtual, 'estado' | 'faixa'>): SeloRisco {
  if (atual.estado === 'indisponivel') return 'indisponivel'
  if (atual.estado === 'desatualizado') return 'desatualizado'
  return ehFaixa(atual.faixa) ? atual.faixa : 'indisponivel'
}
