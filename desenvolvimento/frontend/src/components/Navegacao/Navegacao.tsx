import { BookOpen, Gauge } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import styles from './Navegacao.module.css'

const ITENS = [
  { para: '/', rotulo: 'Painel', Icone: Gauge },
  { para: '/como-funciona', rotulo: 'Como funciona', Icone: BookOpen },
] as const

/** Barra inferior no celular, linha no topo no desktop (Farol, padroes de tela). */
export function Navegacao() {
  return (
    <nav className={styles.nav} aria-label="Principal">
      <ul className={styles.lista}>
        {ITENS.map(({ para, rotulo, Icone }) => (
          <li key={para}>
            <NavLink to={para} end className={styles.item}>
              <Icone aria-hidden="true" size={20} />
              <span>{rotulo}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
