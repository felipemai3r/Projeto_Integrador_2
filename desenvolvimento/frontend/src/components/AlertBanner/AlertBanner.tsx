import { useState } from 'react'
import type { Alerta } from '../../lib/api'
import { formatarNivel } from '../../lib/formato'
import { SELOS, type Faixa } from '../../lib/risco'
import styles from './AlertBanner.module.css'

const ORDEM: Faixa[] = ['normal', 'observacao', 'atencao', 'alerta']
const peso = (f: string) => ORDEM.indexOf(f as Faixa)

interface Props {
  alertas: Alerta[]
}

/**
 * Faixa de alerta vigente (CDU07). Mostra o mais grave. Observacao pode ser dispensada;
 * atencao e alerta ficam enquanto vigentes. Nao pisca. Faixa `alerta` usa `role="alert"`
 * (anuncio imediato); as demais usam `status` (anuncio educado). O texto so e anunciado quando muda.
 */
export function AlertBanner({ alertas }: Props) {
  const [dispensados, setDispensados] = useState<number[]>([])
  const visiveis = alertas
    .filter((a) => a.vigente && !dispensados.includes(a.id))
    .sort((a, b) => peso(b.faixa_nova) - peso(a.faixa_nova))
  const principal = visiveis[0]
  if (!principal || !(principal.faixa_nova in SELOS)) return null

  const faixa = principal.faixa_nova as Faixa
  const { rotulo, Icone } = SELOS[faixa]
  const titulo = `${principal.curso_dagua ?? principal.nome} em ${rotulo.toLowerCase()}`
  const origem = principal.origem === 'previsto' ? 'Previsão' : 'Observado'
  const outros = visiveis.length - 1

  return (
    <section
      className={styles.faixa}
      data-faixa={faixa}
      role={faixa === 'alerta' ? 'alert' : 'status'}
      aria-label="Alerta vigente"
    >
      <Icone aria-hidden="true" size={32} className={styles.icone} />
      <div className={styles.texto}>
        <p className={styles.titulo}>{titulo}</p>
        <p className={styles.detalhe}>
          {principal.nivel_m != null && <>Nível {formatarNivel(principal.nivel_m)} m. </>}
          {origem}.
          {outros > 0 &&
            ` Mais ${outros} alerta${outros > 1 ? 's' : ''} vigente${outros > 1 ? 's' : ''}.`}{' '}
          Fonte oficial: Defesa Civil de Presidente Getúlio.
        </p>
      </div>
      {faixa === 'observacao' && (
        <button
          type="button"
          className={styles.dispensar}
          onClick={() => setDispensados((d) => [...d, principal.id])}
        >
          Dispensar
        </button>
      )}
    </section>
  )
}
