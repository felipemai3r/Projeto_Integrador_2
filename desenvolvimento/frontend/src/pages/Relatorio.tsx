import { useQuery } from '@tanstack/react-query'
import { Printer } from 'lucide-react'
import { useState } from 'react'
import { Botao } from '../components/Botao'
import { RiskBadge } from '../components/RiskBadge'
import { SegmentedControl } from '../components/SegmentedControl'
import { Skeleton } from '../components/Skeleton'
import { useAlertasVigentes, useEstacoes, useNivelAtual, useQualidade } from '../hooks/useDados'
import { api } from '../lib/api'
import { formatarDataHora, formatarMm, formatarNivel, rotuloFonte } from '../lib/formato'
import { rotuloDoImpacto } from '../lib/impacto'
import { seloDe } from '../lib/risco'
import styles from './Relatorio.module.css'

const PERIODOS = [
  { valor: 7, rotulo: '7 dias' },
  { valor: 30, rotulo: '30 dias' },
]

function SituacaoAtual({ codigo }: { codigo: string }) {
  const { data } = useNivelAtual(codigo)
  if (!data) return <Skeleton altura={24} />
  return (
    <tr>
      <th scope="row">{data.estacao.curso_dagua ?? data.estacao.nome}</th>
      <td className={styles.num}>
        {data.nivel_m != null ? `${formatarNivel(data.nivel_m)} m` : '—'}
      </td>
      <td>
        <RiskBadge faixa={seloDe(data)} />
      </td>
      <td>{data.medido_em ? formatarDataHora(data.medido_em) : 'sem leitura'}</td>
    </tr>
  )
}

function NivelNoPeriodo({ codigo, dias }: { codigo: string; dias: number }) {
  const { data } = useQuery({
    queryKey: ['serie-relatorio', codigo, dias],
    queryFn: () => api.serie(codigo, dias * 24),
  })
  if (!data) return <Skeleton altura={40} />
  const v = data.pontos.map((p) => p.valor)
  if (v.length === 0) return <p>Sem leituras no período.</p>
  const media = v.reduce((a, b) => a + b, 0) / v.length
  return (
    <dl className={styles.resumo}>
      <div>
        <dt>Mínimo</dt>
        <dd>{formatarNivel(Math.min(...v))} m</dd>
      </div>
      <div>
        <dt>Média</dt>
        <dd>{formatarNivel(media)} m</dd>
      </div>
      <div>
        <dt>Máximo</dt>
        <dd>{formatarNivel(Math.max(...v))} m</dd>
      </div>
    </dl>
  )
}

/** Relatorio consolidado do periodo (CDU15, RF21). Imprima ou salve como PDF pelo navegador. */
export function Relatorio() {
  const [dias, setDias] = useState(7)
  const estacoes = useEstacoes()
  const vigentes = useAlertasVigentes()
  const qualidade = useQualidade()
  const historico = useQuery({ queryKey: ['alertas-historico'], queryFn: api.alertasHistorico })
  const ocorrencias = useQuery({
    queryKey: ['ocorrencias', dias],
    queryFn: () => api.ocorrencias(dias),
  })
  const alvos = estacoes.data?.filter((e) => e.papel === 'alvo') ?? []
  const [agora] = useState(() => Date.now()) // fixo durante a visita: nao muda a cada render
  const desde = agora - dias * 24 * 3600 * 1000
  const alertasNoPeriodo = (historico.data ?? []).filter(
    (a) => new Date(a.criado_em).getTime() >= desde,
  )

  return (
    <article className={styles.pagina}>
      <div className={`${styles.topo} nao-imprimir`}>
        <h2 className={styles.titulo}>Relatório de situação</h2>
        <Botao onClick={() => window.print()}>
          <Printer aria-hidden="true" size={20} />
          Imprimir ou salvar em PDF
        </Botao>
      </div>
      <h2 className={styles.tituloImpressao}>Rios de Presidente Getúlio: relatório de situação</h2>
      <p className={styles.meta}>
        Período: últimos {dias} dias · Gerado em {formatarDataHora(new Date().toISOString())}
      </p>
      <div className="nao-imprimir">
        <SegmentedControl rotulo="Período" opcoes={PERIODOS} valor={dias} onChange={setDias} />
      </div>

      <section aria-labelledby="r-agora">
        <h3 id="r-agora">Situação agora</h3>
        {vigentes.data && vigentes.data.length > 0 && (
          <p className={styles.destaque}>
            Há {vigentes.data.length} alerta(s) vigente(s):{' '}
            {vigentes.data.map((a) => `${a.curso_dagua ?? a.nome} em ${a.faixa_nova}`).join('; ')}.
          </p>
        )}
        <table className={styles.tabela}>
          <thead>
            <tr>
              <th scope="col">Rio</th>
              <th scope="col" className={styles.num}>
                Nível
              </th>
              <th scope="col">Faixa</th>
              <th scope="col">Leitura</th>
            </tr>
          </thead>
          <tbody>
            {alvos.map((e) => (
              <SituacaoAtual key={e.codigo} codigo={e.codigo} />
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="r-nivel">
        <h3 id="r-nivel">Nível do rio dos Índios no período</h3>
        <NivelNoPeriodo codigo="DCSC-00043" dias={dias} />
      </section>

      <section aria-labelledby="r-alertas">
        <h3 id="r-alertas">Alertas no período</h3>
        {alertasNoPeriodo.length === 0 ? (
          <p>Nenhuma mudança de faixa de risco no período.</p>
        ) : (
          <ul className={styles.lista}>
            {alertasNoPeriodo.map((a) => (
              <li key={a.id}>
                {formatarDataHora(a.criado_em)}: {a.curso_dagua ?? a.nome}, de {a.faixa_anterior}{' '}
                para <strong>{a.faixa_nova}</strong> ({a.origem})
                {a.encerrado_em
                  ? `, encerrado em ${formatarDataHora(a.encerrado_em)}`
                  : ', vigente'}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="r-registros">
        <h3 id="r-registros">Alagamentos registrados pela população (confirmados)</h3>
        {ocorrencias.data?.length === 0 && <p>Nenhum registro confirmado no período.</p>}
        {ocorrencias.data && ocorrencias.data.length > 0 && (
          <ul className={styles.lista}>
            {ocorrencias.data.map((o) => (
              <li key={o.id}>
                {formatarDataHora(o.ocorreu_em)}: {rotuloDoImpacto(o.tipo_impacto)}
                {o.descricao ? ` (${o.descricao})` : ''}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="r-qualidade">
        <h3 id="r-qualidade">Qualidade dos dados</h3>
        {qualidade.data && (
          <ul className={styles.lista}>
            {qualidade.data.fontes
              .filter((f) => f.ultima_coleta)
              .map((f) => (
                <li key={f.codigo}>
                  {rotuloFonte(f.nome)}:{' '}
                  {f.instavel ? `instável (${f.falhas_seguidas} falhas seguidas)` : 'funcionando'}
                </li>
              ))}
            {qualidade.data.estacoes
              .filter((e) => e.variavel === 'nivel_m')
              .map((e) => (
                <li key={e.estacao}>
                  {e.nome}: cobertura de {formatarMm(e.cobertura_24h_pct).replace(',0', '')}% nas
                  últimas 24 h, {e.lacunas_7d} lacuna(s) em 7 dias
                </li>
              ))}
          </ul>
        )}
      </section>

      <p className={styles.rodape}>
        Estimativa de apoio, feita a partir dos dados da Defesa Civil de Santa Catarina. A fonte
        oficial é a Defesa Civil de Presidente Getúlio. Este relatório não substitui os alertas
        oficiais.
      </p>
    </article>
  )
}
