import { Database } from 'lucide-react'
import { formatarDataHora, formatarHora, nomeDaFonte } from '../../lib/formato'
import styles from './SourceStamp.module.css'

interface Props {
  fonte: string | null | undefined
  estacao: string
  medidoEm: string | null | undefined
}

/** Proveniencia de todo dado exibido: fonte, estacao e horario da medicao (RF20, RNF16). */
export function SourceStamp({ fonte, estacao, medidoEm }: Props) {
  if (!fonte || !medidoEm) return null
  return (
    <p className={styles.selo}>
      <Database aria-hidden="true" size={16} />
      <span>
        Fonte: {nomeDaFonte(fonte)} · {estacao} · medido às{' '}
        <time dateTime={medidoEm} title={formatarDataHora(medidoEm)}>
          {formatarHora(medidoEm)}
        </time>
      </span>
    </p>
  )
}
