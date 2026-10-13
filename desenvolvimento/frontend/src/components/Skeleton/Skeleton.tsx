import styles from './Skeleton.module.css'

export function Skeleton({ altura = 16, largura = '100%' }: { altura?: number; largura?: string }) {
  return (
    <span className={styles.bloco} style={{ height: altura, width: largura }} aria-hidden="true" />
  )
}
