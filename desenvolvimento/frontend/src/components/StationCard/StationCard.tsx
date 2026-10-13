import type { NivelAtual } from '../../lib/api'
import { formatarNivel } from '../../lib/formato'
import { seloDe } from '../../lib/risco'
import { LevelGauge } from '../LevelGauge'
import { RiskBadge } from '../RiskBadge'
import { SourceStamp } from '../SourceStamp'
import { StaleNotice } from '../StaleNotice'
import { TrendIndicator } from '../TrendIndicator'
import styles from './StationCard.module.css'

interface Props {
  atual: NivelAtual
}

/** Cartao de situacao de uma estacao alvo (CDU01): o elemento mais importante da tela inicial. */
export function StationCard({ atual }: Props) {
  const { estacao } = atual
  const selo = seloDe(atual)
  const titulo = estacao.curso_dagua ?? estacao.nome
  const idTitulo = `estacao-${estacao.codigo}`

  return (
    <article className={styles.cartao} data-faixa={selo} aria-labelledby={idTitulo}>
      {atual.estado === 'desatualizado' && <StaleNotice ultimaLeituraBoa={atual.medido_em} />}

      <header className={styles.topo}>
        <h3 id={idTitulo} className={styles.nome}>
          {titulo}
        </h3>
        <RiskBadge faixa={selo} size="lg" />
      </header>

      {atual.nivel_m != null ? (
        <>
          <p className={`${styles.nivel} fa-num`}>
            <span className={styles.valor}>{formatarNivel(atual.nivel_m)}</span>
            <span className={styles.unidade}>m</span>
          </p>
          <p className={styles.legenda}>Nível do rio, altura da água em relação ao leito.</p>
          {atual.estado === 'ok' && (
            <TrendIndicator
              tendencia={atual.tendencia}
              taxaCmH={atual.taxa_cm_h}
              aceleracaoCmH2={atual.aceleracao_cm_h2}
            />
          )}
          <LevelGauge nivelM={atual.nivel_m} limiares={estacao.limiares} />
        </>
      ) : (
        <p className={styles.indisponivel}>
          {atual.motivo ?? 'Sem leitura desta estação no momento.'}
        </p>
      )}

      <SourceStamp fonte={atual.fonte} estacao={estacao.codigo} medidoEm={atual.medido_em} />
    </article>
  )
}
