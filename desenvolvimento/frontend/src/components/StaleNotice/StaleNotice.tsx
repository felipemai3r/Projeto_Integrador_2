import { ClockAlert } from 'lucide-react'
import { formatarHora } from '../../lib/formato'
import styles from './StaleNotice.module.css'

interface Props {
  ultimaLeituraBoa: string | null | undefined
}

/** Aviso de dado desatualizado (RN04). Nao some sozinho e nao vira alerta. */
export function StaleNotice({ ultimaLeituraBoa }: Props) {
  return (
    <div className={styles.aviso} role="status">
      <ClockAlert aria-hidden="true" size={20} />
      <p>
        Dado desatualizado.
        {ultimaLeituraBoa ? ` Última leitura boa às ${formatarHora(ultimaLeituraBoa)}.` : ''} Não é
        possível confirmar a situação agora.
      </p>
    </div>
  )
}
