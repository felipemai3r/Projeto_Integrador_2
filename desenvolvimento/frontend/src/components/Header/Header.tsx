import { Moon, Sun } from 'lucide-react'
import { useTema } from '../../hooks/useTema'
import styles from './Header.module.css'

export function Header() {
  const { alternar } = useTema()
  return (
    <header className={styles.cabecalho}>
      <div className={`fa-container ${styles.barra}`}>
        <div>
          <p className={styles.marca}>Rios de Presidente Getúlio</p>
          <p className={styles.sub}>Nível dos rios e chuva, quase em tempo real</p>
        </div>
        <button
          type="button"
          className={styles.tema}
          onClick={alternar}
          aria-label="Alternar modo dia e noite"
        >
          <Sun aria-hidden="true" size={20} className={styles.sol} />
          <Moon aria-hidden="true" size={20} className={styles.lua} />
        </button>
      </div>
    </header>
  )
}
