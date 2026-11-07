import {
  ArrowDownToDot,
  CircleHelp,
  Footprints,
  House,
  Info,
  Mountain,
  OctagonAlert,
  Route,
  Split,
  TriangleAlert,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/**
 * Classificacao das ocorrencias, igual a da API (`api/schemas.py`). Duas categorias: alagamento e
 * movimento de massa (grupo 1.1.3 da COBRADE: quedas, deslizamentos, subsidencias), mais "outro".
 * Movimento de massa traz tambem a gravidade.
 */
export type Categoria = 'alagamento' | 'movimento_massa' | 'outro'

export type TipoImpacto =
  | 'via_intransitavel'
  | 'agua_calcada'
  | 'agua_imovel'
  | 'deslizamento'
  | 'queda_rocha'
  | 'movimentacao_terra'
  | 'outro'

export const IMPACTOS: Record<
  TipoImpacto,
  { rotulo: string; Icone: LucideIcon; categoria: Categoria; dica?: string }
> = {
  via_intransitavel: {
    rotulo: 'Rua ou estrada intransitável',
    Icone: Route,
    categoria: 'alagamento',
  },
  agua_calcada: { rotulo: 'Água na calçada', Icone: Footprints, categoria: 'alagamento' },
  agua_imovel: { rotulo: 'Água dentro de imóvel', Icone: House, categoria: 'alagamento' },
  deslizamento: {
    rotulo: 'Deslizamento de terra ou barranco',
    Icone: Mountain,
    categoria: 'movimento_massa',
    dica: 'Terra, lama ou barranco que desceu',
  },
  queda_rocha: {
    rotulo: 'Queda de pedras ou rochas',
    Icone: ArrowDownToDot,
    categoria: 'movimento_massa',
    dica: 'Pedras que rolaram ou caíram da encosta',
  },
  movimentacao_terra: {
    rotulo: 'Sinais de movimentação de terra',
    Icone: Split,
    categoria: 'movimento_massa',
    dica: 'Rachaduras no chão ou nas paredes, árvores ou postes tortos, chão afundando',
  },
  outro: { rotulo: 'Outro', Icone: CircleHelp, categoria: 'outro' },
}

export const CATEGORIAS: Record<Categoria, { rotulo: string; plural: string }> = {
  alagamento: { rotulo: 'Alagamento', plural: 'Alagamentos' },
  movimento_massa: {
    rotulo: 'Deslizamento ou movimentação de terra',
    plural: 'Deslizamentos e terra',
  },
  outro: { rotulo: 'Outro', plural: 'Outros' },
}

export type Gravidade = 'baixa' | 'media' | 'alta'

export const GRAVIDADES: Record<
  Gravidade,
  { rotulo: string; descricao: string; Icone: LucideIcon }
> = {
  baixa: {
    rotulo: 'Gravidade baixa',
    descricao: 'Pequeno, não atingiu casa nem rua',
    Icone: Info,
  },
  media: {
    rotulo: 'Gravidade média',
    descricao: 'Atingiu rua, quintal ou muro',
    Icone: TriangleAlert,
  },
  alta: {
    rotulo: 'Gravidade alta',
    descricao: 'Atingiu casa ou há pessoas em risco',
    Icone: OctagonAlert,
  },
}

export const tiposDaCategoria = (c: Categoria): TipoImpacto[] =>
  (Object.keys(IMPACTOS) as TipoImpacto[]).filter((t) => IMPACTOS[t].categoria === c)

export const categoriaDoTipo = (tipo: string): Categoria =>
  tipo in IMPACTOS ? IMPACTOS[tipo as TipoImpacto].categoria : 'outro'

/** So deslizamento, queda de pedras e movimentacao de terra pedem a gravidade. */
export const exigeGravidade = (tipo: string): boolean => categoriaDoTipo(tipo) === 'movimento_massa'

export const rotuloDoImpacto = (tipo: string): string =>
  tipo in IMPACTOS ? IMPACTOS[tipo as TipoImpacto].rotulo : tipo

export const ehGravidade = (g: unknown): g is Gravidade => typeof g === 'string' && g in GRAVIDADES
