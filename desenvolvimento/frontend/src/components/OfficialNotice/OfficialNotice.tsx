import { Info } from 'lucide-react'
import styles from './OfficialNotice.module.css'

/** Aviso obrigatorio onde ha risco ou previsao (RN09, RF33). */
export function OfficialNotice() {
  return (
    <aside className={styles.aviso} aria-label="Aviso sobre a fonte oficial">
      <Info aria-hidden="true" size={20} />
      <p>Estimativa de apoio. A fonte oficial é a Defesa Civil de Presidente Getúlio.</p>
    </aside>
  )
}
