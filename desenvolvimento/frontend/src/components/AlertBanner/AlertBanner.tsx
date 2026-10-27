import { useState } from 'react'
import type { Alerta } from '../../lib/api'
import { formatarNivel } from '../../lib/formato'
import { FAIXAS, SELOS, ehFaixa } from '../../lib/risco'
import styles from './AlertBanner.module.css'

const peso = (f: string) => FAIXAS.findIndex((x) => x === f)

interface Props {
  alertas: Alerta[]
}

/**
 * Faixa de alerta vigente (CDU07). Mostra o mais grave. Atencao pode ser dispensada; alerta,
 * alerta alto e extremo ficam enquanto vigentes. Nao pisca. Alerta alto e extremo usam
 * `role="alert"` (anuncio imediato); as demais usam `status` (anuncio educado). O texto so e
 * anunciado quando muda.
 */
export function AlertBanner({ alertas }: Props) {
  const [dispensados, setDispensados] = useState<number[]>([])
  const visiveis = alertas
    .filter((a) => a.vigente && !dispensados.includes(a.id))
    .sort((a, b) => peso(b.faixa_nova) - peso(a.faixa_nova))
  const principal = visiveis[0]
  if (!principal || !ehFaixa(principal.faixa_nova)) return null

  const faixa = principal.faixa_nova
  const { emFrase, Icone } = SELOS[faixa]
  const titulo = `${principal.curso_dagua ?? principal.nome} em ${emFrase}`
  const origem = principal.origem === 'previsto' ? 'Previsão' : 'Observado'
  const outros = visiveis.length - 1

  return (
    <section
      className={styles.faixa}
      data-faixa={faixa}
      role={faixa === 'alerta_alto' || faixa === 'extremo' ? 'alert' : 'status'}
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
      {faixa === 'atencao' && (
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
