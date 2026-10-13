import { SELOS, type Origem, type SeloRisco } from '../../lib/risco'
import styles from './RiskBadge.module.css'

interface Props {
  faixa: SeloRisco
  size?: 'md' | 'lg'
  origem?: Origem
}

/** Selo de faixa de risco. Sempre cor + icone + texto (nunca so cor). */
export function RiskBadge({ faixa, size = 'md', origem = 'observado' }: Props) {
  const { rotulo, Icone } = SELOS[faixa]
  const sufixo = origem === 'previsto' ? ' (previsão)' : origem === 'cenario' ? ' (cenário)' : ''
  return (
    <span className={`${styles.selo} ${size === 'lg' ? styles.lg : ''}`} data-faixa={faixa}>
      <Icone aria-hidden="true" size={size === 'lg' ? 24 : 20} strokeWidth={2} />
      <span>
        {rotulo}
        {sufixo}
      </span>
    </span>
  )
}
