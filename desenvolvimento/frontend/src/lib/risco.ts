import { CircleCheck, CircleOff, ClockAlert, Eye, OctagonAlert, TriangleAlert } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { NivelAtual } from './api'

export type Faixa = 'normal' | 'observacao' | 'atencao' | 'alerta'
export type SeloRisco = Faixa | 'desatualizado' | 'indisponivel'
export type Origem = 'observado' | 'previsto' | 'cenario'

/** Cor nunca vai sozinha: toda faixa tem icone e rotulo (Farol, fundamento 02). */
export const SELOS: Record<SeloRisco, { rotulo: string; Icone: LucideIcon }> = {
  normal: { rotulo: 'Normal', Icone: CircleCheck },
  observacao: { rotulo: 'Observação', Icone: Eye },
  atencao: { rotulo: 'Atenção', Icone: TriangleAlert },
  alerta: { rotulo: 'Alerta', Icone: OctagonAlert },
  desatualizado: { rotulo: 'Dado desatualizado', Icone: ClockAlert },
  indisponivel: { rotulo: 'Indisponível', Icone: CircleOff },
}

const FAIXAS: readonly string[] = ['normal', 'observacao', 'atencao', 'alerta']

/** Dado velho ou ausente nunca pode parecer "normal": o estado do dado vence a faixa. */
export function seloDe(atual: Pick<NivelAtual, 'estado' | 'faixa'>): SeloRisco {
  if (atual.estado === 'indisponivel') return 'indisponivel'
  if (atual.estado === 'desatualizado') return 'desatualizado'
  return atual.faixa && FAIXAS.includes(atual.faixa) ? (atual.faixa as Faixa) : 'indisponivel'
}
