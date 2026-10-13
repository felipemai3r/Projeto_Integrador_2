import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Botao } from '../components/Botao'
import { Skeleton } from '../components/Skeleton'
import { useSessao } from '../hooks/useSessao'
import { api, ErroApi, type OcorrenciaOut } from '../lib/api'
import { formatarDataHora, formatarNivel } from '../lib/formato'
import { IMPACTOS, rotuloDoImpacto, type TipoImpacto } from '../lib/impacto'
import styles from './Moderacao.module.css'

function Login({ entrar }: { entrar: (e: string, s: string) => Promise<void> }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(ev: FormEvent) {
    ev.preventDefault()
    setErro(null)
    setEnviando(true)
    try {
      await entrar(email, senha)
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : 'Não conseguimos entrar agora.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className={styles.login} onSubmit={enviar}>
      <h2 className={styles.titulo}>Área da Defesa Civil</h2>
      <p>Entre para conferir os registros de alagamento.</p>
      <label className={styles.campo}>
        E-mail
        <input
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className={styles.campo}>
        Senha
        <input
          type="password"
          autoComplete="current-password"
          required
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
        />
      </label>
      {erro && (
        <p role="alert" className={styles.erro}>
          {erro}
        </p>
      )}
      <Botao type="submit" bloco disabled={enviando}>
        {enviando ? 'Entrando…' : 'Entrar'}
      </Botao>
    </form>
  )
}

function Foto({ token, id }: { token: string; id: number }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    let alvo: string | null = null
    api
      .fotoProtegida(token, id)
      .then((u) => {
        alvo = u
        setUrl(u)
      })
      .catch(() => setUrl(null))
    return () => {
      if (alvo) URL.revokeObjectURL(alvo)
    }
  }, [token, id])
  return url ? (
    <img className={styles.foto} src={url} alt="Foto enviada por quem registrou" />
  ) : null
}

function Cartao({
  o,
  token,
  aoModerar,
}: {
  o: OcorrenciaOut
  token: string
  aoModerar: () => void
}) {
  const [nota, setNota] = useState('')
  const [novoTipo, setNovoTipo] = useState<TipoImpacto | ''>('')
  const [erro, setErro] = useState<string | null>(null)
  const acao = useMutation({
    mutationFn: (corpo: { acao: string; tipo_impacto?: string; nota?: string }) =>
      api.moderar(token, o.id, corpo),
    onSuccess: aoModerar,
    onError: (e) => setErro(e instanceof ErroApi ? e.message : 'Não conseguimos salvar agora.'),
  })
  const ctx = o.contexto as {
    disponivel?: boolean
    niveis?: Record<string, { nivel_m: number }>
    chuva_24h_mm?: Record<string, number>
  } | null
  const nivel = ctx?.niveis?.['DCSC-00043']

  return (
    <li className={styles.cartao}>
      <div>
        <strong>{rotuloDoImpacto(o.tipo_impacto)}</strong>
        <p className={styles.meta}>
          Ocorreu em {formatarDataHora(o.ocorreu_em)} · enviado em {formatarDataHora(o.criada_em)}
        </p>
        <p className={styles.meta}>
          <a
            href={`https://www.openstreetmap.org/?mlat=${o.latitude}&mlon=${o.longitude}#map=18/${o.latitude}/${o.longitude}`}
            target="_blank"
            rel="noreferrer"
          >
            Ver no mapa ({o.latitude.toFixed(5)}, {o.longitude.toFixed(5)})
          </a>
        </p>
        {o.descricao && <p>{o.descricao}</p>}
        <p className={styles.meta}>
          {ctx?.disponivel
            ? `Condições na hora: ${nivel ? `rio dos Índios em ${formatarNivel(nivel.nivel_m)} m` : 'nível sem leitura'}${ctx.chuva_24h_mm?.['DCSC-00043'] != null ? `, ${ctx.chuva_24h_mm['DCSC-00043']} mm de chuva em 24 h na cidade` : ''}.`
            : 'Sem dados de nível e chuva para esse horário.'}
        </p>
        {o.tem_foto && <Foto token={token} id={o.id} />}
      </div>

      <div className={styles.acoes}>
        <Botao onClick={() => acao.mutate({ acao: 'validar' })} disabled={acao.isPending}>
          Validar
        </Botao>
        <label className={styles.campo}>
          Reclassificar como
          <select value={novoTipo} onChange={(e) => setNovoTipo(e.target.value as TipoImpacto)}>
            <option value="">Escolha…</option>
            {(Object.keys(IMPACTOS) as TipoImpacto[])
              .filter((t) => t !== o.tipo_impacto)
              .map((t) => (
                <option key={t} value={t}>
                  {IMPACTOS[t].rotulo}
                </option>
              ))}
          </select>
        </label>
        <Botao
          variante="secundario"
          disabled={!novoTipo || acao.isPending}
          onClick={() => acao.mutate({ acao: 'reclassificar', tipo_impacto: novoTipo })}
        >
          Reclassificar
        </Botao>
        <label className={styles.campo}>
          Motivo (obrigatório para rejeitar)
          <input value={nota} onChange={(e) => setNota(e.target.value)} />
        </label>
        <Botao
          variante="perigo"
          disabled={!nota.trim() || acao.isPending}
          onClick={() => acao.mutate({ acao: 'rejeitar', nota })}
        >
          Rejeitar
        </Botao>
        {erro && (
          <p role="alert" className={styles.erro}>
            {erro}
          </p>
        )}
      </div>
    </li>
  )
}

function Fila({ token, nome, sair }: { token: string; nome: string; sair: () => void }) {
  const qc = useQueryClient()
  const { data, isPending, error } = useQuery({
    queryKey: ['pendentes', token],
    queryFn: () => api.pendentes(token),
    refetchInterval: 30_000,
  })
  useEffect(() => {
    if (error instanceof ErroApi && error.status === 401) sair()
  }, [error, sair])

  return (
    <div className={styles.pagina}>
      <div className={styles.topo}>
        <h2 className={styles.titulo}>Registros para conferir</h2>
        <p className={styles.meta}>
          {nome} ·{' '}
          <button type="button" className={styles.link} onClick={sair}>
            Sair
          </button>
        </p>
      </div>
      {isPending && <Skeleton altura={160} />}
      {data && data.length === 0 && <p>Nenhum registro esperando conferência.</p>}
      <ul className={styles.lista}>
        {data?.map((o) => (
          <Cartao
            key={o.id}
            o={o}
            token={token}
            aoModerar={() => void qc.invalidateQueries({ queryKey: ['pendentes'] })}
          />
        ))}
      </ul>
    </div>
  )
}

export function Moderacao() {
  const { sessao, entrar, sair } = useSessao()
  return sessao ? (
    <Fila token={sessao.token} nome={sessao.nome} sair={sair} />
  ) : (
    <Login entrar={entrar} />
  )
}
