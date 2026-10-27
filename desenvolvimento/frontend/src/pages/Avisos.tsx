import { useMutation } from '@tanstack/react-query'
import { BellOff, BellRing, Mail, Send } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Botao } from '../components/Botao'
import { Skeleton } from '../components/Skeleton'
import { usePush } from '../hooks/usePush'
import { api, ErroApi } from '../lib/api'
import styles from './Avisos.module.css'

const FAIXAS = [
  { valor: 'atencao', rotulo: 'Atenção (aviso mais cedo)' },
  { valor: 'alerta', rotulo: 'Alerta (recomendado)' },
  { valor: 'alerta_alto', rotulo: 'Alerta alto' },
  { valor: 'extremo', rotulo: 'Risco extremo (limite ainda não definido)' },
]
const ESTACOES = [
  { valor: 'DCSC-00043', rotulo: 'Rio dos Índios' },
  { valor: '', rotulo: 'Todos os rios' },
]

const mensagemDeErro = (e: unknown, padrao: string) => (e instanceof ErroApi ? e.message : padrao)

function Preferencias({
  estacao,
  setEstacao,
  faixa,
  setFaixa,
}: {
  estacao: string
  setEstacao: (v: string) => void
  faixa: string
  setFaixa: (v: string) => void
}) {
  return (
    <>
      <label className={styles.campo}>
        Qual rio
        <select value={estacao} onChange={(e) => setEstacao(e.target.value)}>
          {ESTACOES.map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.rotulo}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.campo}>
        Avisar a partir de
        <select value={faixa} onChange={(e) => setFaixa(e.target.value)}>
          {FAIXAS.map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.rotulo}
            </option>
          ))}
        </select>
      </label>
    </>
  )
}

/** Confirma ou cancela pelo link do e-mail. O POST so acontece aqui, nunca ao abrir o link na API. */
function LinkDoEmail() {
  const [params, setParams] = useSearchParams()
  const confirmar = params.get('confirmar')
  const cancelar = params.get('cancelar')
  const acao = useMutation({
    mutationFn: () =>
      confirmar ? api.confirmarEmail(confirmar) : api.cancelarEmail(cancelar ?? ''),
    onSettled: () => setParams({}, { replace: true }),
  })
  const disparou = useRef(false)
  useEffect(() => {
    if ((confirmar || cancelar) && !disparou.current) {
      disparou.current = true
      acao.mutate()
    }
  }, [confirmar, cancelar, acao])

  if (acao.isPending) return <Skeleton altura={60} />
  if (acao.isSuccess)
    return (
      <p className={styles.ok} role="status">
        {acao.data.mensagem}
      </p>
    )
  if (acao.isError)
    return (
      <p role="alert" className={styles.erro}>
        {mensagemDeErro(acao.error, 'Não conseguimos concluir agora. Tente de novo.')}
      </p>
    )
  return null
}

function AvisosPorEmail() {
  const [email, setEmail] = useState('')
  const [faixa, setFaixa] = useState('alerta')
  const [estacao, setEstacao] = useState('DCSC-00043')
  const envio = useMutation({
    mutationFn: () =>
      api.inscreverEmail({ email: email.trim(), estacao: estacao || null, faixa_minima: faixa }),
  })

  return (
    <section className={styles.secao} aria-labelledby="titulo-email">
      <h3 id="titulo-email" className={styles.subtitulo}>
        <Mail aria-hidden="true" size={20} /> Por e-mail
      </h3>
      <p className={styles.apoio}>
        Funciona em qualquer aparelho. Enviamos um link de confirmação; sem confirmar, nada é
        enviado. Todo aviso traz um link para cancelar, e ao cancelar o e-mail é apagado.
      </p>
      {envio.isSuccess ? (
        <p className={styles.ok} role="status">
          {envio.data.mensagem}
        </p>
      ) : (
        <form
          className={styles.form}
          onSubmit={(e) => {
            e.preventDefault()
            envio.mutate()
          }}
        >
          <label className={styles.campo}>
            Seu e-mail
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <Preferencias
            estacao={estacao}
            setEstacao={setEstacao}
            faixa={faixa}
            setFaixa={setFaixa}
          />
          <Botao type="submit" variante="primario" bloco disabled={envio.isPending}>
            <Mail aria-hidden="true" size={20} />
            {envio.isPending ? 'Enviando…' : 'Receber avisos por e-mail'}
          </Botao>
          {envio.isError && (
            <p role="alert" className={styles.erro}>
              {mensagemDeErro(envio.error, 'Não conseguimos enviar agora. Tente de novo.')}
            </p>
          )}
        </form>
      )}
    </section>
  )
}

function AvisosNoCelular() {
  const { situacao, erro, ocupado, inscrever, cancelar, testar } = usePush()
  const [faixa, setFaixa] = useState('alerta')
  const [estacao, setEstacao] = useState('DCSC-00043')

  return (
    <section className={styles.secao} aria-labelledby="titulo-push">
      <h3 id="titulo-push" className={styles.subtitulo}>
        <BellRing aria-hidden="true" size={20} /> No celular (notificação)
      </h3>

      {situacao === 'carregando' && <Skeleton altura={160} />}

      {situacao === 'nao-suportado' && (
        <p className={styles.aviso} role="status">
          Este navegador não aceita notificações. Tente o Chrome, o Firefox ou o Edge, ou use os
          avisos por e-mail.
        </p>
      )}

      {situacao === 'iphone-sem-instalar' && (
        <div className={styles.aviso} role="status">
          <p>No iPhone, as notificações só funcionam depois de adicionar o app à tela inicial:</p>
          <ol>
            <li>Abra esta página no Safari.</li>
            <li>Toque em Compartilhar e depois em &ldquo;Adicionar à Tela de Início&rdquo;.</li>
            <li>Abra o app pela tela inicial e volte aqui.</li>
          </ol>
        </div>
      )}

      {situacao === 'negado' && (
        <p className={styles.aviso} role="status">
          As notificações estão bloqueadas neste navegador. Para ativar, permita notificações para
          este site nas configurações do navegador e volte aqui.
        </p>
      )}

      {situacao === 'sem-service-worker' && (
        <p className={styles.aviso} role="status">
          As notificações funcionam na versão publicada do app. Em desenvolvimento, use{' '}
          <code>npm run build &amp;&amp; npm run preview</code>. Os avisos por e-mail funcionam aqui
          também.
        </p>
      )}

      {situacao === 'nao-inscrito' && (
        <form
          className={styles.form}
          onSubmit={(e) => {
            e.preventDefault()
            void inscrever(estacao || null, faixa)
          }}
        >
          <Preferencias
            estacao={estacao}
            setEstacao={setEstacao}
            faixa={faixa}
            setFaixa={setFaixa}
          />
          <Botao type="submit" variante="primario" bloco disabled={ocupado}>
            <BellRing aria-hidden="true" size={20} />
            {ocupado ? 'Ativando…' : 'Avisar quando subir'}
          </Botao>
        </form>
      )}

      {situacao === 'inscrito' && (
        <div className={styles.ok} role="status">
          <p>
            <BellRing aria-hidden="true" size={20} /> As notificações estão ativas neste aparelho.
          </p>
          <div className={styles.acoes}>
            <Botao variante="secundario" onClick={() => void testar()} disabled={ocupado}>
              <Send aria-hidden="true" size={20} />
              Enviar aviso de teste
            </Botao>
            <Botao variante="secundario" onClick={() => void cancelar()} disabled={ocupado}>
              <BellOff aria-hidden="true" size={20} />
              Parar de receber
            </Botao>
          </div>
        </div>
      )}

      {erro && (
        <p role="alert" className={styles.erro}>
          {erro}
        </p>
      )}
    </section>
  )
}

export function Avisos() {
  return (
    <section className={styles.pagina} aria-labelledby="titulo-avisos">
      <h2 id="titulo-avisos" className={styles.titulo}>
        Avisos de cheia
      </h2>
      <p className={styles.apoio}>
        Receba um aviso quando o nível do rio subir para uma faixa de risco, e outro quando voltar
        ao normal. O aviso diz o nível, se é observado ou previsão, e lembra que a fonte oficial é a
        Defesa Civil. Ele não substitui os alertas oficiais.
      </p>
      <LinkDoEmail />
      <AvisosPorEmail />
      <AvisosNoCelular />
    </section>
  )
}
