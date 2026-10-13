import styles from './SegmentedControl.module.css'

interface Opcao<T extends string | number> {
  valor: T
  rotulo: string
}

interface Props<T extends string | number> {
  rotulo: string
  opcoes: Opcao<T>[]
  valor: T
  onChange: (valor: T) => void
}

/** Escolha de uma opcao entre poucas (ex.: periodo do grafico). Grupo de radios nativo. */
export function SegmentedControl<T extends string | number>({
  rotulo,
  opcoes,
  valor,
  onChange,
}: Props<T>) {
  return (
    <fieldset className={styles.grupo}>
      <legend className={styles.legenda}>{rotulo}</legend>
      <div className={styles.opcoes}>
        {opcoes.map((o) => (
          <label key={o.valor} className={styles.opcao}>
            <input
              type="radio"
              name={rotulo}
              checked={o.valor === valor}
              onChange={() => onChange(o.valor)}
            />
            <span>{o.rotulo}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
