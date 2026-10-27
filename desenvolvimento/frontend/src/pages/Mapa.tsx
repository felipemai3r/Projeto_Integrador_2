import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Flag, ThumbsUp } from 'lucide-react'
import { renderToStaticMarkup } from 'react-dom/server'
import { useState } from 'react'
import { Marker, Popup } from 'react-leaflet'
import { BotaoLink } from '../components/Botao'
import { MapaBase, iconeDeMarcador } from '../components/MapaBase'
import { SegmentedControl } from '../components/SegmentedControl'
import { Skeleton } from '../components/Skeleton'
import { api, ErroApi, type OcorrenciaOut } from '../lib/api'
import { idDoDispositivo, jaReagi, marcarReacao, type TipoReacao } from '../lib/dispositivo'
import { formatarDataHora, formatarNivel } from '../lib/formato'
import { PERIODO_PADRAO, PERIODOS } from '../lib/periodos'
import { IMPACTOS, rotuloDoImpacto, type TipoImpacto } from '../lib/impacto'
import styles from './Mapa.module.css'

const MOTIVOS = [
  { valor: 'falso', rotulo: 'Não alagou / informação falsa' },
  { valor: 'local_errado', rotulo: 'Local errado' },
  { valor: 'improprio', rotulo: 'Conteúdo impróprio' },
  { valor: 'outro', rotulo: 'Outro motivo' },
]

function icone(tipo: string, pendente: boolean) {
  const Icone = IMPACTOS[(tipo in IMPACTOS ? tipo : 'outro') as TipoImpacto].Icone
  return iconeDeMarcador(
    pendente ? `${styles.marcador} ${styles.pendente}` : styles.marcador!,
    renderToStaticMarkup(<Icone size={20} strokeWidth={2} />),
  )
}

/** Curtir ("vi também") e denunciar, sem login. Uma de cada por aparelho. */
function Reacoes({ o }: { o: OcorrenciaOut }) {
  const cliente = useQueryClient()
  const [curtiu, setCurtiu] = useState(() => jaReagi(o.id, 'curtida'))
  const [denunciou, setDenunciou] = useState(() => jaReagi(o.id, 'denuncia'))
  const [abrirDenuncia, setAbrirDenuncia] = useState(false)
  const [motivo, setMotivo] = useState('')
  const reacao = useMutation({
    mutationFn: ({
      tipo,
      ativa,
      motivo,
    }: {
      tipo: TipoReacao
      ativa: boolean
      motivo?: string
    }) => {
      const corpo = { tipo, dispositivo: idDoDispositivo(), motivo }
      return ativa ? api.reagir(o.id, corpo) : api.desfazerReacao(o.id, corpo)
    },
    onSuccess: (_, { tipo, ativa }) => {
      marcarReacao(o.id, tipo, ativa)
      if (tipo === 'curtida') setCurtiu(ativa)
      else {
        setDenunciou(ativa)
        setAbrirDenuncia(false)
      }
      void cliente.invalidateQueries({ queryKey: ['ocorrencias'] })
    },
  })

  return (
    <div className={styles.reacoes}>
      <div className={styles.botoesReacao}>
        <button
          type="button"
          className={styles.reacao}
          aria-pressed={curtiu}
          disabled={reacao.isPending}
          onClick={() => reacao.mutate({ tipo: 'curtida', ativa: !curtiu })}
        >
          <ThumbsUp aria-hidden="true" size={16} />
          {curtiu ? 'Você curtiu' : 'Curtir'}
          <span className={styles.contagem} aria-label={`${o.curtidas} curtidas`}>
            {o.curtidas}
          </span>
        </button>
        {denunciou ? (
          <button
            type="button"
            className={styles.reacao}
            aria-pressed="true"
            disabled={reacao.isPending}
            onClick={() => reacao.mutate({ tipo: 'denuncia', ativa: false })}
          >
            <Flag aria-hidden="true" size={16} />
            Denunciado · desfazer
          </button>
        ) : (
          <button
            type="button"
            className={styles.reacao}
            aria-expanded={abrirDenuncia}
            onClick={() => setAbrirDenuncia((v) => !v)}
          >
            <Flag aria-hidden="true" size={16} />
            Denunciar
          </button>
        )}
      </div>
      {abrirDenuncia && !denunciou && (
        <form
          className={styles.denuncia}
          onSubmit={(e) => {
            e.preventDefault()
            if (motivo) reacao.mutate({ tipo: 'denuncia', ativa: true, motivo })
          }}
        >
          <label className={styles.campo}>
            Qual o problema?
            <select value={motivo} onChange={(e) => setMotivo(e.target.value)} required>
              <option value="">Escolha…</option>
              {MOTIVOS.map((m) => (
                <option key={m.valor} value={m.valor}>
                  {m.rotulo}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className={styles.reacao} disabled={!motivo || reacao.isPending}>
            Enviar denúncia
          </button>
        </form>
      )}
      {reacao.isError && (
        <p role="alert" className={styles.erroReacao}>
          {reacao.error instanceof ErroApi
            ? reacao.error.message
            : 'Não conseguimos registrar agora. Tente de novo.'}
        </p>
      )}
    </div>
  )
}

function Detalhes({ o }: { o: OcorrenciaOut }) {
  const nivel = (o.contexto as { niveis?: Record<string, { nivel_m: number }> } | null)?.niveis?.[
    'DCSC-00043'
  ]
  return (
    <div className={styles.detalhes}>
      <strong className={styles.tipo}>{rotuloDoImpacto(o.tipo_impacto)}</strong>
      {o.status === 'pendente' && (
        <span className={styles.selo}>Aguardando conferência da Defesa Civil</span>
      )}
      <span className={styles.quando}>{formatarDataHora(o.ocorreu_em)}</span>
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
      <Reacoes o={o} />
    </div>
  )
}

export function Mapa() {
  const [horas, setHoras] = useState(PERIODO_PADRAO)
  const { data, isPending, isError } = useQuery({
    queryKey: ['ocorrencias', horas],
    queryFn: () => api.ocorrencias(horas),
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
        Registros de quem mora aqui. Cada aviso aparece no mapa assim que é enviado, marcado como
        &ldquo;aguardando conferência&rdquo; até a Defesa Civil confirmar. Curta se você também viu,
        ou denuncie se a informação estiver errada.
      </p>
      <SegmentedControl rotulo="Período" opcoes={PERIODOS} valor={horas} onChange={setHoras} />

      <MapaBase rotulo="Mapa dos alagamentos registrados">
        {data?.map((o) => (
          <Marker
            key={o.id}
            position={[o.latitude, o.longitude]}
            icon={icone(o.tipo_impacto, o.status === 'pendente')}
          >
            <Popup>
              <Detalhes o={o} />
            </Popup>
          </Marker>
        ))}
      </MapaBase>

      <ul className={styles.legenda} aria-label="Legenda do mapa">
        <li>
          <span className={styles.amostra} aria-hidden="true" /> Confirmado pela Defesa Civil
        </li>
        <li>
          <span className={`${styles.amostra} ${styles.pendente}`} aria-hidden="true" /> Aguardando
          conferência
        </li>
      </ul>

      {isPending && <Skeleton altura={80} />}
      {isError && <p>Não conseguimos carregar os registros agora.</p>}
      {data && data.length === 0 && (
        <p className={styles.vazio}>
          Nenhum alagamento registrado neste período. Se alagou perto de você, registre: leva menos
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
