import { formatarNivel } from '../../lib/formato'
import styles from './LevelGauge.module.css'

interface Props {
  nivelM: number
  limiares: { observacao?: number | null; atencao?: number | null; alerta?: number | null }
}

/** Regua do nivel com os tres limiares oficiais (RN01) e o marcador atual. */
export function LevelGauge({ nivelM, limiares }: Props) {
  const { observacao, atencao, alerta } = limiares
  if (observacao == null || atencao == null || alerta == null) return null

  const maximo = Math.max(alerta * 1.15, nivelM * 1.05)
  const pct = (v: number) => Math.min(100, Math.max(0, (v / maximo) * 100))
  const faixaAtual =
    nivelM >= alerta
      ? 'alerta'
      : nivelM >= atencao
        ? 'atenção'
        : nivelM >= observacao
          ? 'observação'
          : 'normal'
  const descricao = `Nível ${formatarNivel(nivelM)} metros, faixa ${faixaAtual}. Limiares: observação ${formatarNivel(observacao)}, atenção ${formatarNivel(atencao)}, alerta ${formatarNivel(alerta)} metros.`

  const trechos = [
    { cor: 'normal', ate: observacao },
    { cor: 'observacao', ate: atencao },
    { cor: 'atencao', ate: alerta },
    { cor: 'alerta', ate: maximo },
  ] as const
  let inicio = 0
  return (
    <div className={styles.regua}>
      <div className={styles.barra} role="img" aria-label={descricao}>
        {trechos.map((t) => {
          const largura = pct(t.ate) - pct(inicio)
          inicio = t.ate
          return <span key={t.cor} data-faixa={t.cor} style={{ width: `${largura}%` }} />
        })}
        {[observacao, atencao, alerta].map((v) => (
          <span key={v} className={styles.limiar} style={{ left: `${pct(v)}%` }} />
        ))}
        <span className={styles.marcador} style={{ left: `${pct(nivelM)}%` }} />
      </div>
      <ul className={styles.legenda}>
        <li>Observação {formatarNivel(observacao)} m</li>
        <li>Atenção {formatarNivel(atencao)} m</li>
        <li>Alerta {formatarNivel(alerta)} m</li>
      </ul>
    </div>
  )
}
