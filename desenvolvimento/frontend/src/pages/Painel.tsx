import { RainAccumulatedTable } from '../components/RainAccumulatedTable'
import { Skeleton } from '../components/Skeleton'
import { StationCard } from '../components/StationCard'
import { useChuvaAcumulada, useEstacoes, useNivelAtual } from '../hooks/useDados'
import styles from './Painel.module.css'

function CartaoDaEstacao({ codigo }: { codigo: string }) {
  const { data, isPending, isError, refetch } = useNivelAtual(codigo)
  if (isPending) return <Skeleton altura={280} />
  if (isError)
    return (
      <div className={styles.erro} role="alert">
        <p>Não conseguimos carregar esta estação agora.</p>
        <button type="button" className={styles.botao} onClick={() => void refetch()}>
          Tentar de novo
        </button>
      </div>
    )
  return <StationCard atual={data} />
}

export function Painel() {
  const estacoes = useEstacoes()
  const chuva = useChuvaAcumulada()
  const alvos = estacoes.data?.filter((e) => e.papel === 'alvo') ?? []
  const pontos = chuva.data?.filter((e) => e.papel !== 'alvo' && e.estado !== 'indisponivel') ?? []

  return (
    <div className={styles.painel}>
      <section aria-labelledby="titulo-rios">
        <h2 id="titulo-rios" className={styles.titulo}>
          Situação dos rios agora
        </h2>
        <div className={styles.cartoes}>
          {estacoes.isPending && <Skeleton altura={280} />}
          {estacoes.isError && (
            <div className={styles.erro} role="alert">
              <p>Não conseguimos carregar as estações agora.</p>
              <button
                type="button"
                className={styles.botao}
                onClick={() => void estacoes.refetch()}
              >
                Tentar de novo
              </button>
            </div>
          )}
          {alvos.map((e) => (
            <CartaoDaEstacao key={e.codigo} codigo={e.codigo} />
          ))}
        </div>
      </section>

      <section aria-labelledby="titulo-chuva">
        <h2 id="titulo-chuva" className={styles.titulo}>
          Chuva nos pontos a montante
        </h2>
        <p className={styles.apoio}>
          O que chove nos pontos acima da cidade chega ao rio horas depois. Veja quanto já choveu.
        </p>
        {chuva.isPending && <Skeleton altura={200} />}
        {chuva.isError && (
          <div className={styles.erro} role="alert">
            <p>Não conseguimos carregar a chuva agora.</p>
          </div>
        )}
        {chuva.data && <RainAccumulatedTable estacoes={pontos} />}
      </section>
    </div>
  )
}
