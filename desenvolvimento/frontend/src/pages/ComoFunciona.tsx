import { useCorrelacao } from '../hooks/useDados'
import { formatarDataHora } from '../lib/formato'
import { SELOS, type SeloRisco } from '../lib/risco'
import { RiskBadge } from '../components/RiskBadge'
import { Skeleton } from '../components/Skeleton'
import styles from './ComoFunciona.module.css'

const FAIXAS: { selo: SeloRisco; texto: string }[] = [
  {
    selo: 'normal',
    texto: 'O nível está abaixo de todos os limites que preocupam a Defesa Civil.',
  },
  { selo: 'observacao', texto: 'O nível chegou ao primeiro limite. É hora de acompanhar.' },
  {
    selo: 'atencao',
    texto: 'O nível chegou ao segundo limite. Fique atento e evite áreas baixas.',
  },
  {
    selo: 'alerta',
    texto: 'O nível chegou ao limite mais alto. Siga as orientações da Defesa Civil.',
  },
  {
    selo: 'desatualizado',
    texto:
      'A fonte parou de enviar dados. Mostramos a última leitura boa e não dá para confirmar a situação.',
  },
  { selo: 'indisponivel', texto: 'Não há leitura desta estação.' },
]

export function ComoFunciona() {
  const { data, isPending, isError } = useCorrelacao()
  const chuvaLocal = data?.find((c) => c.explicativa === 'chuva_bruta' && c.ponto === 'DCSC-00043')
  const aMontante = data?.filter(
    (c) => c.explicativa === 'chuva_sem_local' && c.ponto !== 'DCSC-00020',
  )
  const algumSinal = aMontante?.some((c) => c.sinal_claro) ?? false

  return (
    <article className={styles.pagina}>
      <h2 className={styles.titulo}>Como funciona</h2>

      <section>
        <h3>O que é este sistema</h3>
        <p>
          Mostra como estão o rio dos Índios e o ribeirão Revólver em Presidente Getúlio e quanto
          choveu nos pontos acima da cidade. É uma ferramenta de apoio, feita por estudantes da
          UDESC. <strong>Não substitui a Defesa Civil.</strong> A fonte oficial é a Defesa Civil de
          Presidente Getúlio.
        </p>
      </section>

      <section>
        <h3>De onde vêm os números</h3>
        <p>
          Das estações de medição da Defesa Civil de Santa Catarina, lidas a cada 5 minutos. Embaixo
          de cada número aparece a fonte, a estação e o horário da leitura. Se uma estação para de
          enviar dados, avisamos em vez de esconder.
        </p>
      </section>

      <section>
        <h3>O que significam as cores</h3>
        <p>
          A cor nunca vem sozinha: toda faixa tem também um ícone e uma palavra. Os limites são os
          mesmos usados pela Defesa Civil municipal.
        </p>
        <ul className={styles.faixas}>
          {FAIXAS.map(({ selo, texto }) => (
            <li key={selo}>
              <RiskBadge faixa={selo} />
              <span className={styles.sr}>{SELOS[selo].rotulo}:</span>
              <p>{texto}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="analise">
        <h3 id="analise">O que a análise dos dados mostra até agora</h3>
        {isPending && <Skeleton altura={120} />}
        {isError && <p>Não conseguimos carregar a análise agora.</p>}
        {data && data.length === 0 && <p>A análise ainda não foi calculada.</p>}
        {data && data.length > 0 && (
          <>
            <ul className={styles.achados}>
              {chuvaLocal && (
                <li>
                  O rio dos Índios reage à chuva que cai na própria cidade em cerca de{' '}
                  <strong>{chuvaLocal.melhor_defasagem_h} hora</strong> ou menos. A bacia é pequena
                  e responde rápido.
                </li>
              )}
              <li>
                {algumSinal
                  ? 'Há indício de que a chuva em algum ponto acima da cidade acrescenta efeito, mas é fraco.'
                  : 'Depois de descontar a chuva que cai na cidade, não encontramos relação clara entre a chuva nos pontos acima (Dona Emma, José Boiteux, Witmarsum, Vitor Meireles) e a subida do rio. Isso não prova que não exista: temos poucos meses de dados e poucas cheias fortes.'}
              </li>
              <li>
                A hipótese de que a chuva forte em Dona Emma e José Boiteux <em>ao mesmo tempo</em>{' '}
                faz a cidade alagar ainda <strong>não pôde ser confirmada nem descartada</strong>. A
                análise melhora a cada semana, conforme os dados se acumulam.
              </li>
            </ul>
            <details className={styles.detalhes}>
              <summary>Ver os números da análise</summary>
              <div className={styles.rolagem}>
                <table className={styles.tabela}>
                  <caption>
                    Calculado em {formatarDataHora(data[0]!.calculado_em)}, últimos 90 dias
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Ponto</th>
                      <th scope="col">Análise</th>
                      <th scope="col" className={styles.num}>
                        Defasagem
                      </th>
                      <th scope="col" className={styles.num}>
                        Correlação
                      </th>
                      <th scope="col">Leitura</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((c) => (
                      <tr key={`${c.explicativa}-${c.ponto}`}>
                        <th scope="row">{c.nome.replace(/^PCD |^SDC-SC /, '')}</th>
                        <td>{NOME_ANALISE[c.explicativa] ?? c.explicativa}</td>
                        <td className={styles.num}>{c.melhor_defasagem_h} h</td>
                        <td className={styles.num}>{c.r.toFixed(2).replace('.', ',')}</td>
                        <td>{c.sinal_claro ? 'Há relação' : 'Sem relação clara'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </section>

      <section>
        <h3>O que o sistema ainda não faz</h3>
        <p>
          Não prevê o nível do rio nem diz quais ruas alagam. Ninguém tem hoje o registro de cota
          por rua em Presidente Getúlio, e prometer isso sem validação seria irresponsável. O
          caminho é construir esse dado com a ajuda de quem mora aqui.
        </p>
      </section>
    </article>
  )
}

const NOME_ANALISE: Record<string, string> = {
  chuva_bruta: 'Chuva no ponto',
  chuva_sem_local: 'Chuva no ponto, sem a chuva local',
  nivel: 'Nível do rio no ponto',
}
