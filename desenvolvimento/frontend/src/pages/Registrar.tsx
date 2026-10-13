import { useMutation } from '@tanstack/react-query'
import { LocateFixed } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Botao, BotaoLink } from '../components/Botao'
import { MapaBase } from '../components/MapaBase'
import { SeletorDePonto, type Ponto } from '../components/SeletorDePonto'
import { api, ErroApi } from '../lib/api'
import { IMPACTOS, type TipoImpacto } from '../lib/impacto'
import styles from './Registrar.module.css'

const TIPOS = Object.keys(IMPACTOS) as TipoImpacto[]

export function Registrar() {
  const [ponto, setPonto] = useState<Ponto | null>(null)
  const [agora, setAgora] = useState(true)
  const [quando, setQuando] = useState('')
  const [tipo, setTipo] = useState<TipoImpacto | ''>('')
  const [descricao, setDescricao] = useState('')
  const [foto, setFoto] = useState<File | null>(null)
  // limite do campo de data: agora, no horario local (o servidor tambem recusa data futura)
  const [maximo] = useState(() =>
    new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16),
  )
  const [erroLocal, setErroLocal] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  const envio = useMutation({
    mutationFn: (dados: FormData) => api.registrarOcorrencia(dados),
  })

  function usarMinhaLocalizacao() {
    setAviso(null)
    if (!('geolocation' in navigator)) {
      setAviso('Este aparelho não informa a localização. Toque no mapa para marcar o ponto.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (p) => setPonto({ lat: p.coords.latitude, lon: p.coords.longitude }),
      () => setAviso('Não conseguimos pegar a sua localização. Toque no mapa para marcar o ponto.'),
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  function enviar(e: FormEvent) {
    e.preventDefault()
    setErroLocal(null)
    if (!ponto) return setErroLocal('Toque no mapa para marcar onde alagou.')
    if (!tipo) return setErroLocal('Escolha o que aconteceu.')
    if (!agora && !quando)
      return setErroLocal('Informe quando foi, ou marque "Está acontecendo agora".')
    const dados = new FormData()
    dados.set('latitude', String(ponto.lat))
    dados.set('longitude', String(ponto.lon))
    dados.set('ocorreu_em', (agora ? new Date() : new Date(quando)).toISOString())
    dados.set('tipo_impacto', tipo)
    if (descricao.trim()) dados.set('descricao', descricao.trim())
    if (foto) dados.set('foto', foto)
    envio.mutate(dados)
  }

  if (envio.isSuccess) {
    return (
      <section className={styles.sucesso} role="status">
        <h2 className={styles.titulo}>Obrigado!</h2>
        <p>{envio.data.mensagem}</p>
        <p>
          Se houver risco agora, ligue para a Defesa Civil: <strong>199</strong>. Em emergência
          grave, <strong>193</strong> (Bombeiros).
        </p>
        <BotaoLink to="/mapa">Ver o mapa</BotaoLink>
      </section>
    )
  }

  const erro =
    erroLocal ??
    (envio.error instanceof ErroApi
      ? envio.error.message
      : envio.error
        ? 'Não conseguimos enviar agora. Tente de novo.'
        : null)

  return (
    <form className={styles.form} onSubmit={enviar} noValidate>
      <h2 className={styles.titulo}>Registrar alagamento</h2>
      <p className={styles.apoio}>
        Não precisa de cadastro e o seu nome não aparece. Cada registro é conferido pela Defesa
        Civil. Em situação de risco, ligue <strong>199</strong>.
      </p>

      <fieldset className={styles.grupo}>
        <legend>1. Onde alagou</legend>
        <MapaBase rotulo="Mapa para marcar onde alagou. Toque no ponto.">
          <SeletorDePonto ponto={ponto} onChange={setPonto} />
        </MapaBase>
        <Botao variante="secundario" onClick={usarMinhaLocalizacao}>
          <LocateFixed aria-hidden="true" size={20} />
          Usar a minha localização
        </Botao>
        {ponto && <p className={styles.ok}>Ponto marcado. Toque em outro lugar para mudar.</p>}
        {aviso && (
          <p role="status" className={styles.aviso}>
            {aviso}
          </p>
        )}
      </fieldset>

      <fieldset className={styles.grupo}>
        <legend>2. Quando</legend>
        <label className={styles.linha}>
          <input type="checkbox" checked={agora} onChange={(e) => setAgora(e.target.checked)} />
          Está acontecendo agora
        </label>
        {!agora && (
          <label className={styles.campo}>
            Data e hora
            <input
              type="datetime-local"
              value={quando}
              max={maximo}
              onChange={(e) => setQuando(e.target.value)}
            />
          </label>
        )}
      </fieldset>

      <fieldset className={styles.grupo}>
        <legend>3. O que aconteceu</legend>
        <div className={styles.tipos}>
          {TIPOS.map((t) => {
            const { rotulo, Icone } = IMPACTOS[t]
            return (
              <label key={t} className={styles.tipo}>
                <input type="radio" name="tipo" checked={tipo === t} onChange={() => setTipo(t)} />
                <Icone aria-hidden="true" size={24} />
                <span>{rotulo}</span>
              </label>
            )
          })}
        </div>
      </fieldset>

      <fieldset className={styles.grupo}>
        <legend>4. Se quiser, conte mais</legend>
        <label className={styles.campo}>
          Foto (opcional)
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => setFoto(e.target.files?.[0] ?? null)}
          />
          <small>Tiramos da foto qualquer dado de localização do aparelho.</small>
        </label>
        <label className={styles.campo}>
          Descrição (opcional)
          <textarea
            rows={3}
            maxLength={500}
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
          />
          <small>{descricao.length} de 500 caracteres</small>
        </label>
      </fieldset>

      {erro && (
        <p role="alert" className={styles.erro}>
          {erro}
        </p>
      )}
      <Botao type="submit" variante="primario" bloco disabled={envio.isPending}>
        {envio.isPending ? 'Enviando…' : 'Enviar registro'}
      </Botao>
    </form>
  )
}
