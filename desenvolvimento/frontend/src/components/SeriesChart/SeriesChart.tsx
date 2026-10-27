import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSerie } from '../../hooks/useDados'
import { formatarDataHora, formatarHora, formatarNivel } from '../../lib/formato'
import { PERIODO_PADRAO, PERIODOS } from '../../lib/periodos'
import type { Limiares } from '../../lib/risco'
import { SegmentedControl } from '../SegmentedControl'
import { Skeleton } from '../Skeleton'
import styles from './SeriesChart.module.css'

interface Props {
  codigo: string
  titulo: string
  limiares: Limiares
}

/** Linhas de limiar do grafico. O rotulo e curto; `extremo` so aparece quando houver cota. */
const MARCOS = [
  { faixa: 'atencao', rotulo: 'Atenção', cor: 'var(--fa-risk-atencao-border)' },
  { faixa: 'alerta', rotulo: 'Alerta', cor: 'var(--fa-risk-alerta-border)' },
  { faixa: 'alerta_alto', rotulo: 'Alerta alto', cor: 'var(--fa-risk-alerta-alto-border)' },
  { faixa: 'extremo', rotulo: 'Extremo', cor: 'var(--fa-risk-extremo-border)' },
] as const

/** Historico do nivel (RF18). Observado = linha cheia; limiares como linhas rotuladas. */
export function SeriesChart({ codigo, titulo, limiares }: Props) {
  const [horas, setHoras] = useState(PERIODO_PADRAO)
  const { data, isPending, isError } = useSerie(codigo, horas)

  const pontos = data?.pontos ?? []
  const valores = pontos.map((p) => p.valor)
  const maximo = valores.length ? Math.max(...valores) : 0
  const minimo = valores.length ? Math.min(...valores) : 0
  const dominio: [number, number] = [
    Math.max(0, +(minimo - 0.1).toFixed(2)),
    +(maximo + 0.1).toFixed(2),
  ]
  const proximo = MARCOS.map((m) => limiares[m.faixa]).find(
    (l): l is number => l != null && l > maximo,
  )
  const ultimo = pontos.at(-1)
  const resumo = ultimo
    ? `Nível ${formatarNivel(ultimo.valor)} m. Mínimo ${formatarNivel(minimo)} m e máximo ${formatarNivel(maximo)} m no período.`
    : 'Sem leituras no período.'
  const formatarX = (iso: string) => (horas > 24 ? formatarDataHora(iso) : formatarHora(iso))

  return (
    <section className={styles.bloco} aria-labelledby={`grafico-${codigo}`}>
      <div className={styles.topo}>
        <h3 id={`grafico-${codigo}`} className={styles.titulo}>
          {titulo}
        </h3>
        <SegmentedControl rotulo="Período" opcoes={PERIODOS} valor={horas} onChange={setHoras} />
      </div>

      {isPending && <Skeleton altura={240} />}
      {isError && <p className={styles.aviso}>Não conseguimos carregar o histórico agora.</p>}
      {data && pontos.length === 0 && <p className={styles.aviso}>Sem leituras neste período.</p>}
      {pontos.length > 0 && (
        <>
          <div className={styles.grafico} role="img" aria-label={resumo}>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={pontos} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid
                  stroke="var(--fa-data-grid)"
                  strokeDasharray="3 3"
                  vertical={false}
                />
                <XAxis
                  dataKey="medido_em"
                  tickFormatter={formatarX}
                  tick={{ fill: 'var(--fa-color-content-secondary)', fontSize: 12 }}
                  minTickGap={48}
                  stroke="var(--fa-color-border-strong)"
                />
                <YAxis
                  domain={dominio}
                  width={44}
                  tickFormatter={(v: number) => formatarNivel(v)}
                  tick={{ fill: 'var(--fa-color-content-secondary)', fontSize: 12 }}
                  stroke="var(--fa-color-border-strong)"
                />
                <Tooltip
                  labelFormatter={(v) => formatarDataHora(String(v))}
                  formatter={(v) => [`${formatarNivel(Number(v))} m`, 'Nível']}
                  contentStyle={{
                    background: 'var(--fa-color-surface-base)',
                    border: '1px solid var(--fa-color-border-default)',
                    borderRadius: 10,
                    color: 'var(--fa-color-content-primary)',
                  }}
                />
                {MARCOS.map(({ faixa, rotulo, cor }) => {
                  const v = limiares[faixa]
                  return v != null && v >= dominio[0] && v <= dominio[1] ? (
                    <ReferenceLine
                      key={faixa}
                      y={v}
                      stroke={cor}
                      strokeDasharray="4 4"
                      label={{
                        value: `${rotulo} ${formatarNivel(v)} m`,
                        fill: 'var(--fa-color-content-secondary)',
                        fontSize: 12,
                        position: 'insideTopRight',
                      }}
                    />
                  ) : null
                })}
                <Line
                  type="monotone"
                  dataKey="valor"
                  stroke="var(--fa-data-observed)"
                  strokeWidth={3}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className={styles.resumo}>
            {resumo}
            {proximo != null && ultimo && (
              <> Faltam {formatarNivel(proximo - ultimo.valor)} m para a próxima faixa de risco.</>
            )}
          </p>
          <details className={styles.detalhes}>
            <summary>Ver os valores em tabela</summary>
            <table className={styles.tabela}>
              <thead>
                <tr>
                  <th scope="col">Horário</th>
                  <th scope="col" className={styles.num}>
                    Nível (m)
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...pontos]
                  .reverse()
                  .slice(0, 48)
                  .map((p) => (
                    <tr key={p.medido_em}>
                      <td>{formatarDataHora(p.medido_em)}</td>
                      <td className={styles.num}>{formatarNivel(p.valor)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  )
}
