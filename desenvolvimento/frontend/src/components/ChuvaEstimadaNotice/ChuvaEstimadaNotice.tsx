import { CloudOff } from 'lucide-react'
import type { ChuvaEstimada } from '../../lib/api'
import styles from './ChuvaEstimadaNotice.module.css'

const semPrefixo = (nome: string) => nome.replace(/^PCD\s+/, '')

/**
 * Aviso de chuva estimada: um ponto ficou sem leitura e a previsao usou a media dos outros.
 * Nao some sozinho; a incerteza maior precisa ficar a vista (RN03).
 */
export function ChuvaEstimadaNotice({ pontos }: { pontos: ChuvaEstimada[] }) {
  if (pontos.length === 0) return null
  return (
    <div className={styles.aviso} role="status">
      <CloudOff aria-hidden="true" size={20} />
      <div>
        {pontos.map((p) => (
          <p key={p.codigo}>
            Sem leitura de chuva em {semPrefixo(p.nome)} por {p.horas} h.
          </p>
        ))}
        <p>
          Para essas horas usamos a média dos outros pontos medidos, por isso a previsão é menos
          precisa.
        </p>
      </div>
    </div>
  )
}
