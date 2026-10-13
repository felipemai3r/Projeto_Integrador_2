import type { ReactNode } from 'react'
import styles from './RegiaoRolavel.module.css'

/**
 * Area com rolagem horizontal (tabelas largas no celular). Precisa receber foco por teclado para
 * quem nao usa mouse conseguir rolar (axe: scrollable-region-focusable, WCAG 2.1.1). A regra
 * jsx-a11y/no-noninteractive-tabindex nao conhece esse caso; a excecao fica so aqui.
 */
export function RegiaoRolavel({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className={styles.rolagem} tabIndex={0} role="region" aria-label={rotulo}>
      {children}
    </div>
  )
}
