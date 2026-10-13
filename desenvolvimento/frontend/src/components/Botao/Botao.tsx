import type { ButtonHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import styles from './Botao.module.css'

type Variante = 'primario' | 'secundario' | 'destaque' | 'perigo'

const classe = (v: Variante, bloco?: boolean) =>
  `${styles.botao} ${styles[v]} ${bloco ? styles.bloco : ''}`

/** Botao do Farol. `destaque` (laranja) aparece no maximo uma vez por tela. */
export function Botao({
  variante = 'primario',
  bloco,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; bloco?: boolean }) {
  return <button type="button" className={classe(variante, bloco)} {...props} />
}

export function BotaoLink({
  variante = 'primario',
  bloco,
  ...props
}: LinkProps & { variante?: Variante; bloco?: boolean }) {
  return <Link className={classe(variante, bloco)} {...props} />
}
