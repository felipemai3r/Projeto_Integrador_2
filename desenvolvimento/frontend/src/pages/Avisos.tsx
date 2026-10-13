import { BellOff, BellRing } from 'lucide-react'
import { useState } from 'react'
import { Botao } from '../components/Botao'
import { Skeleton } from '../components/Skeleton'
import { usePush } from '../hooks/usePush'
import styles from './Avisos.module.css'

const FAIXAS = [
  { valor: 'observacao', rotulo: 'Observação (aviso mais cedo)' },
  { valor: 'atencao', rotulo: 'Atenção (recomendado)' },
  { valor: 'alerta', rotulo: 'Só no Alerta' },
]
const ESTACOES = [
  { valor: 'DCSC-00043', rotulo: 'Rio dos Índios' },
  { valor: '', rotulo: 'Todos os rios' },
]

export function Avisos() {
  const { situacao, erro, ocupado, inscrever, cancelar } = usePush()
  const [faixa, setFaixa] = useState('atencao')
  const [estacao, setEstacao] = useState('DCSC-00043')

  return (
    <section className={styles.pagina} aria-labelledby="titulo-avisos">
      <h2 id="titulo-avisos" className={styles.titulo}>
        Avisos no celular
      </h2>
      <p className={styles.apoio}>
        Receba uma notificação quando o nível do rio subir para uma faixa de risco. Não precisa de
        cadastro: guardamos só o necessário para enviar o aviso a este aparelho, e você cancela
        quando quiser.
      </p>

      {situacao === 'carregando' && <Skeleton altura={160} />}

      {situacao === 'nao-suportado' && (
        <p className={styles.aviso} role="status">
          Este navegador não aceita avisos. Tente o Chrome, o Firefox ou o Edge, ou acompanhe pelo
          painel.
        </p>
      )}

      {situacao === 'iphone-sem-instalar' && (
        <div className={styles.aviso} role="status">
          <p>No iPhone, os avisos só funcionam depois de adicionar o app à tela inicial:</p>
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
          Os avisos funcionam na versão publicada do app. Em desenvolvimento, use{' '}
          <code>npm run build &amp;&amp; npm run preview</code>.
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
          <p className={styles.nota}>
            O aviso diz o nível, se é observado ou previsão, e lembra que a fonte oficial é a Defesa
            Civil. Ele não substitui os alertas oficiais.
          </p>
          <Botao type="submit" variante="primario" bloco disabled={ocupado}>
            <BellRing aria-hidden="true" size={20} />
            {ocupado ? 'Ativando…' : 'Avisar quando subir'}
          </Botao>
        </form>
      )}

      {situacao === 'inscrito' && (
        <div className={styles.ok} role="status">
          <p>
            <BellRing aria-hidden="true" size={20} /> Os avisos estão ativos neste aparelho.
          </p>
          <Botao variante="secundario" onClick={() => void cancelar()} disabled={ocupado}>
            <BellOff aria-hidden="true" size={20} />
            Parar de receber avisos
          </Botao>
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
