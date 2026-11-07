import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Flag, ThumbsUp } from 'lucide-react'
import { renderToStaticMarkup } from 'react-dom/server'
import { useState } from 'react'
import { Marker, Popup } from 'react-leaflet'
import { BotaoLink } from '../components/Botao'
import { MapaBase, iconeDeMarcador } from '../components/MapaBase'
import { SegmentedControl } from '../components/SegmentedControl'
import { SeloGravidade } from '../components/SeloGravidade'
import { Skeleton } from '../components/Skeleton'
import { api, ErroApi, type OcorrenciaOut } from '../lib/api'
import { idDoDispositivo, jaReagi, marcarReacao, type TipoReacao } from '../lib/dispositivo'
import { formatarDataHora, formatarMm, formatarNivel } from '../lib/formato'
import { PERIODO_PADRAO, PERIODOS } from '../lib/periodos'
import {
  CATEGORIAS,
  IMPACTOS,
  categoriaDoTipo,
  ehGravidade,
  rotuloDoImpacto,
  type Categoria,
  type TipoImpacto,
} from '../lib/impacto'
import styles from './Mapa.module.css'

const MOTIVOS = [
  { valor: 'falso', rotulo: 'Não aconteceu / informação falsa' },
  { valor: 'local_errado', rotulo: 'Local errado' },
  { valor: 'improprio', rotulo: 'Conteúdo impróprio' },
  { valor: 'outro', rotulo: 'Outro motivo' },
]

type Filtro = 'todas' | Categoria

const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: 'todas', rotulo: 'Todas' },
  { valor: 'alagamento', rotulo: CATEGORIAS.alagamento.plural },
  { valor: 'movimento_massa', rotulo: CATEGORIAS.movimento_massa.plural },
]

/** Estacao da cidade: referencia de nivel e de chuva no detalhe de cada registro. */
const ESTACAO_CIDADE = 'DCSC-00043'

/** Forma diz a categoria (circulo = agua, quadrado = terra); o icone diz o tipo. */
function icone(tipo: string, pendente: boolean) {
  const Icone = IMPACTOS[(tipo in IMPACTOS ? tipo : 'outro') as TipoImpacto].Icone
  const classes = [
    styles.marcador,
    categoriaDoTipo(tipo) === 'movimento_massa' && styles.terra,
    pendente && styles.pendente,
  ]
  return iconeDeMarcador(
    classes.filter(Boolean).join(' '),
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

interface Contexto {
  niveis?: Record<string, { nivel_m: number }>
  chuva_24h_mm?: Record<string, number>
  chuva_72h_mm?: Record<string, number>
}

/** Agua: o nivel do rio na hora. Terra: a chuva acumulada antes, que encharca a encosta. */
function FraseDeContexto({ o }: { o: OcorrenciaOut }) {
  const ctx = o.contexto as Contexto | null
  if (o.categoria === 'movimento_massa') {
    const mm72 = ctx?.chuva_72h_mm?.[ESTACAO_CIDADE]
    const mm24 = ctx?.chuva_24h_mm?.[ESTACAO_CIDADE]
    if (mm72 == null && mm24 == null) return null
    return (
      <p className={styles.contexto}>
        Chuva na cidade antes do registro:{' '}
        {[
          mm24 != null && `${formatarMm(mm24)} mm em 24 horas`,
          mm72 != null && `${formatarMm(mm72)} mm em 3 dias`,
        ]
          .filter(Boolean)
          .join(', ')}
        .
      </p>
    )
  }
  const nivel = ctx?.niveis?.[ESTACAO_CIDADE]
  if (!nivel) return null
  return (
    <p className={styles.contexto}>
      Nesse momento, o rio dos Índios estava em {formatarNivel(nivel.nivel_m)} m.
    </p>
  )
}

function Detalhes({ o }: { o: OcorrenciaOut }) {
  return (
    <div className={styles.detalhes}>
      <span className={styles.categoria}>{CATEGORIAS[categoriaDoTipo(o.tipo_impacto)].rotulo}</span>
      <strong className={styles.tipo}>{rotuloDoImpacto(o.tipo_impacto)}</strong>
      {ehGravidade(o.gravidade) && <SeloGravidade gravidade={o.gravidade} />}
      {o.status === 'pendente' && (
        <span className={styles.selo}>Aguardando conferência da Defesa Civil</span>
      )}
      <span className={styles.quando}>{formatarDataHora(o.ocorreu_em)}</span>
      {o.descricao && <p className={styles.descricao}>{o.descricao}</p>}
      <FraseDeContexto o={o} />
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
  const [filtro, setFiltro] = useState<Filtro>('todas')
  const {
    data: todas,
    isPending,
    isError,
  } = useQuery({
    queryKey: ['ocorrencias', horas],
    queryFn: () => api.ocorrencias(horas),
  })
  const data = todas?.filter((o) => filtro === 'todas' || o.categoria === filtro)
  const nomeDoFiltro = filtro === 'todas' ? 'ocorrência' : CATEGORIAS[filtro].rotulo.toLowerCase()

  return (
    <div className={styles.pagina}>
      <div className={styles.topo}>
        <h2 className={styles.titulo}>Mapa de ocorrências</h2>
        <BotaoLink to="/registrar" variante="destaque">
          Registrar ocorrência
        </BotaoLink>
      </div>
      <p className={styles.apoio}>
        Alagamentos, deslizamentos e sinais de movimentação de terra registrados por quem mora aqui.
        Cada aviso aparece no mapa assim que é enviado, marcado como &ldquo;aguardando
        conferência&rdquo; até a Defesa Civil confirmar. Curta se você também viu, ou denuncie se a
        informação estiver errada.
      </p>
      <SegmentedControl rotulo="Mostrar" opcoes={FILTROS} valor={filtro} onChange={setFiltro} />
      <SegmentedControl rotulo="Período" opcoes={PERIODOS} valor={horas} onChange={setHoras} />

      <MapaBase rotulo="Mapa das ocorrências registradas">
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
          <span className={styles.amostra} aria-hidden="true" /> Alagamento (círculo)
        </li>
        <li>
          <span className={`${styles.amostra} ${styles.terra}`} aria-hidden="true" /> Deslizamento
          ou movimentação de terra (quadrado)
        </li>
        <li>
          <span className={`${styles.amostra} ${styles.neutra}`} aria-hidden="true" /> Preenchido:
          confirmado pela Defesa Civil
        </li>
        <li>
          <span
            className={`${styles.amostra} ${styles.neutra} ${styles.pendente}`}
            aria-hidden="true"
          />{' '}
          Contorno tracejado: aguardando conferência
        </li>
      </ul>

      {isPending && <Skeleton altura={80} />}
      {isError && <p>Não conseguimos carregar os registros agora.</p>}
      {data && data.length === 0 && (
        <p className={styles.vazio}>
          Nenhum registro de {nomeDoFiltro} neste período. Se aconteceu perto de você, registre:
          leva menos de um minuto.
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
