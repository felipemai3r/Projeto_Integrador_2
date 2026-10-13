import type { ChuvaEstacao } from '../../lib/api'
import { formatarHora, formatarMm } from '../../lib/formato'
import styles from './RainAccumulatedTable.module.css'

const JANELAS = ['1h', '3h', '6h', '12h', '24h', '48h', '72h'] as const

interface Props {
  estacoes: ChuvaEstacao[]
}

/** Chuva acumulada por ponto de influencia e janela (RF17). Tabela no desktop, cartoes no celular. */
export function RainAccumulatedTable({ estacoes }: Props) {
  return (
    <table className={styles.tabela}>
      <caption className={styles.legenda}>Chuva acumulada, em milímetros</caption>
      <thead>
        <tr>
          <th scope="col">Ponto</th>
          {JANELAS.map((j) => (
            <th key={j} scope="col" className={styles.num}>
              {j}
            </th>
          ))}
          <th scope="col">Leitura</th>
        </tr>
      </thead>
      <tbody>
        {estacoes.map((e) => (
          <tr key={e.estacao} data-estado={e.estado}>
            <th scope="row">
              {e.nome.replace(/^PCD |^SDC-SC /, '')}
              {e.estado === 'desatualizado' && (
                <span className={styles.aviso}> (desatualizado)</span>
              )}
            </th>
            {JANELAS.map((j) => {
              const v = e.acumulado_mm[j]
              return (
                <td key={j} data-rotulo={j} className={styles.num}>
                  {v == null ? '—' : formatarMm(v)}
                </td>
              )
            })}
            <td data-rotulo="Leitura" className={styles.hora}>
              {e.medido_em ? formatarHora(e.medido_em) : 'sem dado'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
