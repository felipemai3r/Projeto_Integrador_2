import { CircleCheck, TriangleAlert } from 'lucide-react'
import { Skeleton } from '../components/Skeleton'
import { useQualidade } from '../hooks/useDados'
import { formatarDataHora, tempoRelativo } from '../lib/formato'
import styles from './Qualidade.module.css'

const VARIAVEL: Record<string, string> = { nivel_m: 'Nível do rio', chuva_acumulada_mm: 'Chuva' }

function Situacao({ ok, textoOk, textoRuim }: { ok: boolean; textoOk: string; textoRuim: string }) {
  const Icone = ok ? CircleCheck : TriangleAlert
  return (
    <span className={ok ? styles.ok : styles.ruim}>
      <Icone aria-hidden="true" size={16} />
      {ok ? textoOk : textoRuim}
    </span>
  )
}

/** Qualidade dos dados (RF36): o que esta chegando, o que falhou e onde ha buracos. */
export function Qualidade() {
  const { data, isPending, isError } = useQualidade()
  return (
    <article className={styles.pagina}>
      <h2 className={styles.titulo}>Qualidade dos dados</h2>
      <p className={styles.apoio}>
        Aqui mostramos, sem esconder, o que está chegando das fontes e onde há falhas. Dado com
        problema não vira alerta.
      </p>
      {isPending && <Skeleton altura={200} />}
      {isError && <p>Não conseguimos carregar agora.</p>}
      {data && (
        <>
          <section aria-labelledby="fontes">
            <h3 id="fontes">Fontes de dados</h3>
            <div className={styles.rolagem}>
              <table className={styles.tabela}>
                <thead>
                  <tr>
                    <th scope="col">Fonte</th>
                    <th scope="col">Situação</th>
                    <th scope="col">Última coleta</th>
                  </tr>
                </thead>
                <tbody>
                  {data.fontes.map((f) => (
                    <tr key={f.codigo}>
                      <th scope="row">{f.nome}</th>
                      <td>
                        {f.ultima_coleta == null ? (
                          <span className={styles.neutro}>Ainda não usada</span>
                        ) : (
                          <Situacao
                            ok={!f.instavel}
                            textoOk="Funcionando"
                            textoRuim={`Instável (${f.falhas_seguidas} falhas seguidas)`}
                          />
                        )}
                      </td>
                      <td>{f.ultima_coleta ? tempoRelativo(f.ultima_coleta) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="estacoes">
            <h3 id="estacoes">Estações</h3>
            <div className={styles.rolagem}>
              <table className={styles.tabela}>
                <caption>Cobertura nas últimas 24 horas e lacunas nos últimos 7 dias</caption>
                <thead>
                  <tr>
                    <th scope="col">Estação</th>
                    <th scope="col">Dado</th>
                    <th scope="col" className={styles.num}>
                      Cobertura 24 h
                    </th>
                    <th scope="col" className={styles.num}>
                      Lacunas 7 d
                    </th>
                    <th scope="col" className={styles.num}>
                      Maior lacuna
                    </th>
                    <th scope="col">Sensor</th>
                    <th scope="col">Última leitura</th>
                  </tr>
                </thead>
                <tbody>
                  {data.estacoes.map((e) => (
                    <tr key={`${e.estacao}-${e.variavel}`}>
                      <th scope="row">{e.nome.replace(/^PCD |^SDC-SC /, '')}</th>
                      <td>{VARIAVEL[e.variavel] ?? e.variavel}</td>
                      <td className={styles.num}>{e.cobertura_24h_pct.toFixed(0)}%</td>
                      <td className={styles.num}>{e.lacunas_7d}</td>
                      <td className={styles.num}>
                        {e.maior_lacuna_min > 0 ? `${e.maior_lacuna_min} min` : '—'}
                      </td>
                      <td>
                        {e.variavel === 'nivel_m' ? (
                          <Situacao
                            ok={!e.possivelmente_travado}
                            textoOk="Variando"
                            textoRuim="Possivelmente travado"
                          />
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>{e.ultima_leitura ? formatarDataHora(e.ultima_leitura) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={styles.nota}>
              Uma lacuna é um intervalo de mais de 15 minutos sem leitura. As leituras são esperadas
              a cada 5 minutos.
            </p>
          </section>
        </>
      )}
    </article>
  )
}
