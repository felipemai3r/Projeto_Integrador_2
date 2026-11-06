import { Clock, TriangleAlert } from 'lucide-react'
import type { PrevisaoHorizonte, PrevisaoOut } from '../../lib/api'
import { formatarDataHora, formatarNivel } from '../../lib/formato'
import { ehFaixa, type Origem } from '../../lib/risco'
import { ChuvaEstimadaNotice } from '../ChuvaEstimadaNotice'
import { RiskBadge } from '../RiskBadge'
import styles from './PrevisaoTabela.module.css'

function Linha({ h, origem }: { h: PrevisaoHorizonte; origem: Origem }) {
  const extrapola = h.extrapolacao.length > 0
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
              Entre {formatarNivel(h.intervalo_m[0])} e {formatarNivel(h.intervalo_m[1])} m (
              {Math.round((h.confianca ?? 0.95) * 100)}% de confiança)
            </p>
          )}
          {/* Fora do que o modelo ja viu (ex.: chuva maior que qualquer uma do historico), ele
              nao sabe estimar alem e tende a subestimar: mostrar "Normal" seria tranquilizar sem
              base. Nesse caso a faixa nao aparece, so o aviso. */}
          {extrapola ? (
            <p className={styles.extrapolacao} role="note">
              <TriangleAlert aria-hidden="true" size={16} /> Passa do que já foi observado (por
              exemplo, chuva maior que qualquer uma do histórico). O modelo não sabe estimar além
              disso: o nível real pode ser bem maior. Trate este valor como um mínimo, não como
              garantia.
            </p>
          ) : (
            ehFaixa(h.faixa) && <RiskBadge faixa={h.faixa} origem={origem} />
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

/**
 * Previsao por horizonte (CDU02/CDU03). Onde nao ha modelo publicado, diz por que (RN07).
 * Mostra tambem o aviso de chuva estimada, na previsao e no cenario.
 */
export function PrevisaoTabela({ previsao }: { previsao: PrevisaoOut }) {
  const origem: Origem = previsao.origem === 'cenario' ? 'cenario' : 'previsto'
  return (
    <>
      <ChuvaEstimadaNotice pontos={previsao.chuva_estimada ?? []} />
      <ul className={styles.lista}>
        {previsao.horizontes.map((h) => (
          <Linha key={h.horizonte_h} h={h} origem={origem} />
        ))}
      </ul>
    </>
  )
}
