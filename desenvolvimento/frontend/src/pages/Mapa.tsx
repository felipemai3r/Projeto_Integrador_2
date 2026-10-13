import { useQuery } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { useState } from 'react'
import { Marker, Popup } from 'react-leaflet'
import { BotaoLink } from '../components/Botao'
import { MapaBase, iconeDeMarcador } from '../components/MapaBase'
import { SegmentedControl } from '../components/SegmentedControl'
import { Skeleton } from '../components/Skeleton'
import { api, type OcorrenciaOut } from '../lib/api'
import { formatarDataHora, formatarNivel } from '../lib/formato'
import { IMPACTOS, rotuloDoImpacto, type TipoImpacto } from '../lib/impacto'
import styles from './Mapa.module.css'

const PERIODOS = [
  { valor: 30, rotulo: '30 dias' },
  { valor: 365, rotulo: '1 ano' },
]

function icone(tipo: string) {
  const Icone = IMPACTOS[(tipo in IMPACTOS ? tipo : 'outro') as TipoImpacto].Icone
  return iconeDeMarcador(
    styles.marcador!,
    renderToStaticMarkup(<Icone size={20} strokeWidth={2} />),
  )
}

function Detalhes({ o }: { o: OcorrenciaOut }) {
  const nivel = (o.contexto as { niveis?: Record<string, { nivel_m: number }> } | null)?.niveis?.[
    'DCSC-00043'
  ]
  return (
    <>
      <strong>{rotuloDoImpacto(o.tipo_impacto)}</strong>
      <br />
      {formatarDataHora(o.ocorreu_em)}
      {o.descricao && <p className={styles.descricao}>{o.descricao}</p>}
      {nivel && (
        <p className={styles.contexto}>
          Nesse momento, o rio dos Índios estava em {formatarNivel(nivel.nivel_m)} m.
        </p>
      )}
      {o.tem_foto && (
        <img
          className={styles.foto}
          src={`/api/ocorrencias/${o.id}/foto`}
          alt="Foto enviada por quem registrou"
          loading="lazy"
        />
      )}
    </>
  )
}

export function Mapa() {
  const [dias, setDias] = useState(30)
  const { data, isPending, isError } = useQuery({
    queryKey: ['ocorrencias', dias],
    queryFn: () => api.ocorrencias(dias),
  })

  return (
    <div className={styles.pagina}>
      <div className={styles.topo}>
        <h2 className={styles.titulo}>Onde alagou</h2>
        <BotaoLink to="/registrar" variante="destaque">
          Registrar alagamento
        </BotaoLink>
      </div>
      <p className={styles.apoio}>
        Registros de quem mora aqui, conferidos pela Defesa Civil antes de aparecerem. Eles ajudam a
        construir o mapa de onde a água chega, que hoje não existe.
      </p>
      <SegmentedControl rotulo="Período" opcoes={PERIODOS} valor={dias} onChange={setDias} />

      <MapaBase rotulo="Mapa dos alagamentos registrados">
        {data?.map((o) => (
          <Marker key={o.id} position={[o.latitude, o.longitude]} icon={icone(o.tipo_impacto)}>
            <Popup>
              <Detalhes o={o} />
            </Popup>
          </Marker>
        ))}
      </MapaBase>

      {isPending && <Skeleton altura={80} />}
      {isError && <p>Não conseguimos carregar os registros agora.</p>}
      {data && data.length === 0 && (
        <p className={styles.vazio}>
          Nenhum alagamento confirmado neste período. Se alagou perto de você, registre: leva menos
          de um minuto.
        </p>
      )}
      {data && data.length > 0 && (
        <section aria-labelledby="lista-ocorrencias">
          <h3 id="lista-ocorrencias" className={styles.subtitulo}>
            Lista dos registros ({data.length})
          </h3>
          <ul className={styles.lista}>
            {data.map((o) => (
              <li key={o.id}>
                <Detalhes o={o} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
