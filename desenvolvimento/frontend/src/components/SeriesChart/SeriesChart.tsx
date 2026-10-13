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
import { SegmentedControl } from '../SegmentedControl'
import { Skeleton } from '../Skeleton'
import styles from './SeriesChart.module.css'

interface Limiares {
  observacao?: number | null
  atencao?: number | null
  alerta?: number | null
}

interface Props {
  codigo: string
  titulo: string
  limiares: Limiares
}

const PERIODOS = [
  { valor: 6, rotulo: '6 h' },
  { valor: 24, rotulo: '24 h' },
  { valor: 72, rotulo: '3 dias' },
  { valor: 168, rotulo: '7 dias' },
]

/** Historico do nivel (RF18). Observado = linha cheia; limiares como linhas rotuladas. */
export function SeriesChart({ codigo, titulo, limiares }: Props) {
  const [horas, setHoras] = useState(24)
  const { data, isPending, isError } = useSerie(codigo, horas)

  const pontos = data?.pontos ?? []
  const valores = pontos.map((p) => p.valor)
  const maximo = valores.length ? Math.max(...valores) : 0
  const minimo = valores.length ? Math.min(...valores) : 0
  const dominio: [number, number] = [
    Math.max(0, +(minimo - 0.1).toFixed(2)),
    +(maximo + 0.1).toFixed(2),
  ]
  const proximo = [limiares.observacao, limiares.atencao, limiares.alerta].find(
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
                {(
                  [
                    ['Observação', limiares.observacao],
                    ['Atenção', limiares.atencao],
                    ['Alerta', limiares.alerta],
                  ] as const
                ).map(([nome, v]) =>
                  v != null && v >= dominio[0] && v <= dominio[1] ? (
                    <ReferenceLine
                      key={nome}
                      y={v}
                      stroke="var(--fa-color-border-strong)"
                      strokeDasharray="4 4"
                      label={{
                        value: `${nome} ${formatarNivel(v)} m`,
                        fill: 'var(--fa-color-content-secondary)',
                        fontSize: 12,
                        position: 'insideTopRight',
                      }}
                    />
                  ) : null,
                )}
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
