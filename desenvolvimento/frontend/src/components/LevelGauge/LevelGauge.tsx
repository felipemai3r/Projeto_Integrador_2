import { formatarNivel } from '../../lib/formato'
import { faixaDoNivel, SELOS, type Faixa, type Limiares } from '../../lib/risco'
import styles from './LevelGauge.module.css'

interface Props {
  nivelM: number
  limiares: Limiares
}

/**
 * Regua do nivel com os limiares oficiais (RN01) e o marcador atual. Precisa de atencao, alerta
 * e alerta alto; o extremo so entra quando a Defesa Civil cadastrar a cota.
 */
export function LevelGauge({ nivelM, limiares }: Props) {
  const { atencao, alerta, alerta_alto: alertaAlto, extremo } = limiares
  if (atencao == null || alerta == null || alertaAlto == null) return null

  const maximo = Math.max((extremo ?? alertaAlto) * 1.15, nivelM * 1.05)
  const pct = (v: number) => Math.min(100, Math.max(0, (v / maximo) * 100))
  const faixaAtual = SELOS[faixaDoNivel(nivelM, limiares)].emFrase
  const marcos: { faixa: Faixa; valor: number }[] = [
    { faixa: 'atencao', valor: atencao },
    { faixa: 'alerta', valor: alerta },
    { faixa: 'alerta_alto', valor: alertaAlto },
    ...(extremo != null ? [{ faixa: 'extremo' as const, valor: extremo }] : []),
  ]
  const descricao = `Nível ${formatarNivel(nivelM)} metros, faixa ${faixaAtual}. Limiares: ${marcos
    .map((m) => `${SELOS[m.faixa].emFrase} ${formatarNivel(m.valor)}`)
    .join(', ')} metros.`

  // cada trecho vai do marco anterior ao proximo; o ultimo vai ate o fim da regua
  const trechos = [
    { faixa: 'normal' as Faixa, de: 0 },
    ...marcos.map((m) => ({ faixa: m.faixa, de: m.valor })),
  ]
  return (
    <div className={styles.regua}>
      <div className={styles.barra} role="img" aria-label={descricao}>
        {trechos.map((t, i) => {
          const ate = trechos[i + 1]?.de ?? maximo
          return (
            <span
              key={t.faixa}
              data-faixa={t.faixa}
              style={{ width: `${pct(ate) - pct(t.de)}%` }}
            />
          )
        })}
        {marcos.map((m) => (
          <span key={m.faixa} className={styles.limiar} style={{ left: `${pct(m.valor)}%` }} />
        ))}
        <span className={styles.marcador} style={{ left: `${pct(nivelM)}%` }} />
      </div>
      <ul className={styles.legenda}>
        {marcos.map((m) => (
          <li key={m.faixa}>
            {SELOS[m.faixa].rotulo} {formatarNivel(m.valor)} m
          </li>
        ))}
      </ul>
    </div>
  )
}
