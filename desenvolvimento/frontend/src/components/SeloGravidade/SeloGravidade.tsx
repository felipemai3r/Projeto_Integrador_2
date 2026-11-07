import { GRAVIDADES, type Gravidade } from '../../lib/impacto'
import styles from './SeloGravidade.module.css'

/** Gravidade de um deslizamento ou movimentação de terra: cor, ícone e texto juntos. */
export function SeloGravidade({ gravidade }: { gravidade: Gravidade }) {
  const { rotulo, descricao, Icone } = GRAVIDADES[gravidade]
  return (
    <span className={`${styles.selo} ${styles[gravidade]}`} title={descricao}>
      <Icone aria-hidden="true" size={16} />
      {rotulo}
    </span>
  )
}
