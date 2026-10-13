import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { descreverTendencia } from '../../lib/formato'
import styles from './TrendIndicator.module.css'

interface Props {
  tendencia: string | null | undefined
  taxaCmH: number | null | undefined
  aceleracaoCmH2?: number | null
}

/** Tendencia do nivel: icone + texto com numero. Nunca depende so da seta. */
export function TrendIndicator({ tendencia, taxaCmH, aceleracaoCmH2 }: Props) {
  const texto = descreverTendencia(tendencia, taxaCmH, aceleracaoCmH2)
  if (!texto) return <p className={styles.tendencia}>Tendência indisponível</p>
  const Icone =
    tendencia === 'subindo' ? TrendingUp : tendencia === 'descendo' ? TrendingDown : Minus
  return (
    <p className={styles.tendencia}>
      <Icone aria-hidden="true" size={20} />
      <span>{texto}</span>
    </p>
  )
}
