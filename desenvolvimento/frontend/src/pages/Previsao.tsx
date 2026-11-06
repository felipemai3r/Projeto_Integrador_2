import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Botao } from '../components/Botao'
import { PrevisaoTabela } from '../components/PrevisaoTabela'
import { Skeleton } from '../components/Skeleton'
import { usePrevisao } from '../hooks/useDados'
import { api, ErroApi } from '../lib/api'
import { formatarDataHora, formatarNivel } from '../lib/formato'
import styles from './Previsao.module.css'

const ALVO = 'DCSC-00043'
// Nome amigavel por codigo. A LISTA de pontos vem da API (`pontos_cenario`): sao os pontos que o
// modelo publicado usa. Chuva digitada num ponto fora do modelo seria ignorada em silencio.
const NOMES: Record<string, string> = {
  'DCSC-00043': 'Presidente Getúlio (na cidade)',
  'DCSC-00037': 'Dona Emma',
  'DCSC-00021': 'José Boiteux',
  'DCSC-00015': 'Witmarsum',
  'DCSC-00036': 'Vitor Meireles',
  'DCSC-00174': 'Ribeirão Revólver (Creche)',
  'DC-PEU-003': 'Serra dos Índios',
  'DC-PEU-004': 'Serra Vencida',
  'DC-PEU-002': 'Serra Mirador',
}
type Ponto = { codigo: string; nome: string }
const nomeDoPonto = (p: Ponto) => NOMES[p.codigo] ?? p.nome.replace(/^(PCD|SDC-SC)\s+/, '')
const JANELAS = [1, 3, 6, 12, 24]

function Simulador({ pontos }: { pontos: Ponto[] }) {
  const [chuva, setChuva] = useState<Record<string, string>>({})
  const [janela, setJanela] = useState(6)
  const [erroLocal, setErroLocal] = useState<string | null>(null)
  const sim = useMutation({ mutationFn: api.simular })

  function enviar(e: FormEvent) {
    e.preventDefault()
    setErroLocal(null)
    const mm: Record<string, number> = {}
    for (const [cod, v] of Object.entries(chuva)) {
      if (v.trim() === '') continue
      const n = Number(v.replace(',', '.'))
      if (!Number.isFinite(n) || n < 0 || n > 400) {
        return setErroLocal('Digite um valor entre 0 e 400 mm em cada campo.')
      }
      mm[cod] = n
    }
    if (Object.keys(mm).length === 0)
      return setErroLocal('Preencha a chuva em pelo menos um ponto.')
    sim.mutate({ chuva_mm: mm, janela_h: janela, estacao: ALVO })
  }

  const erro =
    erroLocal ??
    (sim.error instanceof ErroApi
      ? sim.error.message
      : sim.error
        ? 'Não conseguimos simular agora.'
        : null)

  return (
    <section aria-labelledby="simulador" className={styles.bloco}>
      <h3 id="simulador" className={styles.subtitulo}>
        Simular uma chuva
      </h3>
      <p className={styles.apoio}>
        Veja o efeito estimado no rio dos Índios se tivesse chovido uma quantidade diferente. É um{' '}
        <strong>cenário hipotético</strong>: não muda nenhum dado e não é uma previsão.
      </p>
      <form className={styles.form} onSubmit={enviar} noValidate>
        {pontos.map((p) => (
          <label key={p.codigo} className={styles.campo}>
            {nomeDoPonto(p)}, em milímetros
            <input
              inputMode="decimal"
              value={chuva[p.codigo] ?? ''}
              onChange={(e) => setChuva({ ...chuva, [p.codigo]: e.target.value })}
              placeholder="0"
            />
          </label>
        ))}
        <label className={styles.campo}>
          Essa chuva caiu em
          <select value={janela} onChange={(e) => setJanela(Number(e.target.value))}>
            {JANELAS.map((j) => (
              <option key={j} value={j}>
                {j === 1 ? '1 hora' : `${j} horas`}
              </option>
            ))}
          </select>
        </label>
        {erro && (
          <p role="alert" className={styles.erro}>
            {erro}
          </p>
        )}
        <Botao type="submit" bloco disabled={sim.isPending}>
          {sim.isPending ? 'Calculando…' : 'Simular'}
        </Botao>
      </form>
      {sim.data && (
        <div role="status" className={styles.resultado}>
          <p className={styles.selo}>Cenário hipotético. Não é uma previsão.</p>
          {sim.data.nivel_base_m != null && (
            <p className={styles.meta}>
              Nível agora: {formatarNivel(sim.data.nivel_base_m)} m
              {sim.data.base_em && ` (${formatarDataHora(sim.data.base_em)})`}
            </p>
          )}
          <PrevisaoTabela previsao={sim.data} />
        </div>
      )}
    </section>
  )
}

export function Previsao() {
  const { data, isPending, isError } = usePrevisao(ALVO)
  const algumaDisponivel = data?.horizontes.some((h) => h.disponivel) ?? false
  return (
    <div className={styles.pagina}>
      <h2 className={styles.titulo}>Previsão do nível</h2>
      <p className={styles.apoio}>
        Estimativa do nível do rio dos Índios para as próximas horas, com a margem de erro. Só
        mostramos um horário quando o modelo provou, em teste, errar menos do que simplesmente
        repetir o nível de agora.
      </p>
      {isPending && <Skeleton altura={240} />}
      {isError && <p>Não conseguimos carregar a previsão agora.</p>}
      {data && (
        <>
          {!algumaDisponivel && (
            <p className={styles.aviso} role="status">
              A previsão ainda não está disponível. Precisamos de mais dados para estimar com
              segurança. Enquanto isso, o painel mostra o que está sendo medido.
            </p>
          )}
          <PrevisaoTabela previsao={data} />
        </>
      )}
      {data && (data.pontos_cenario?.length ?? 0) > 0 && (
        <Simulador pontos={data.pontos_cenario ?? []} />
      )}
    </div>
  )
}
