import { Clock, TriangleAlert } from 'lucide-react'
import type { PrevisaoHorizonte, PrevisaoOut } from '../../lib/api'
import { formatarDataHora, formatarNivel } from '../../lib/formato'
import { ehFaixa, type Origem } from '../../lib/risco'
import { RiskBadge } from '../RiskBadge'
import styles from './PrevisaoTabela.module.css'

function Linha({ h, origem }: { h: PrevisaoHorizonte; origem: Origem }) {
  return (
    <li className={styles.linha}>
      <div className={styles.horizonte}>
        <strong>Daqui a {h.horizonte_h} h</strong>
        {h.valido_para && <span className={styles.meta}>{formatarDataHora(h.valido_para)}</span>}
      </div>
      {h.disponivel && h.nivel_m != null ? (
        <div className={styles.valor}>
          <p className={`${styles.nivel} fa-num`}>
            {formatarNivel(h.nivel_m)} <small>m</small>
          </p>
          {h.intervalo_m && (
            <p className={styles.meta}>
              Entre {formatarNivel(h.intervalo_m[0])} e {formatarNivel(h.intervalo_m[1])} m (95% de
              confiança)
            </p>
          )}
          {ehFaixa(h.faixa) && <RiskBadge faixa={h.faixa} origem={origem} />}
          {h.extrapolacao.length > 0 && (
            <p className={styles.extrapolacao} role="note">
              <TriangleAlert aria-hidden="true" size={16} /> Este cenário está fora do que já foi
              observado. A estimativa tem confiança baixa.
            </p>
          )}
        </div>
      ) : (
        <p className={styles.indisponivel}>
          <Clock aria-hidden="true" size={16} /> {h.motivo ?? 'Ainda não disponível.'}
        </p>
      )}
    </li>
  )
}

/** Previsao por horizonte (CDU02/CDU03). Onde nao ha modelo publicado, diz por que (RN07). */
export function PrevisaoTabela({ previsao }: { previsao: PrevisaoOut }) {
  const origem: Origem = previsao.origem === 'cenario' ? 'cenario' : 'previsto'
  return (
    <ul className={styles.lista}>
      {previsao.horizontes.map((h) => (
        <Linha key={h.horizonte_h} h={h} origem={origem} />
      ))}
    </ul>
  )
}
