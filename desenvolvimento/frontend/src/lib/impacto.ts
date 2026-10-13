import { CircleHelp, Footprints, House, Route } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export type TipoImpacto = 'via_intransitavel' | 'agua_calcada' | 'agua_imovel' | 'outro'

export const IMPACTOS: Record<TipoImpacto, { rotulo: string; Icone: LucideIcon }> = {
  via_intransitavel: { rotulo: 'Rua ou estrada intransitável', Icone: Route },
  agua_calcada: { rotulo: 'Água na calçada', Icone: Footprints },
  agua_imovel: { rotulo: 'Água dentro de imóvel', Icone: House },
  outro: { rotulo: 'Outro', Icone: CircleHelp },
}

export const rotuloDoImpacto = (tipo: string): string =>
  tipo in IMPACTOS ? IMPACTOS[tipo as TipoImpacto].rotulo : tipo
