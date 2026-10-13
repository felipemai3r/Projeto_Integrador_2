const FUSO = 'America/Sao_Paulo'

const numero2 = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const numero1 = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
const inteiro = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const hora = new Intl.DateTimeFormat('pt-BR', {
  hour: '2-digit',
  minute: '2-digit',
  timeZone: FUSO,
})
const dataHora = new Intl.DateTimeFormat('pt-BR', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: FUSO,
})

export const formatarNivel = (m: number): string => numero2.format(m)
export const formatarMm = (mm: number): string => numero1.format(mm)
export const formatarHora = (iso: string): string => hora.format(new Date(iso))
export const formatarDataHora = (iso: string): string => dataHora.format(new Date(iso))

/** "há 5 min", "há 2 h". `agora` e injetavel para teste. */
export function tempoRelativo(iso: string, agora: Date = new Date()): string {
  const min = Math.max(0, Math.round((agora.getTime() - new Date(iso).getTime()) / 60000))
  if (min < 1) return 'agora há pouco'
  if (min < 60) return `há ${min} min`
  const h = Math.round(min / 60)
  if (h < 48) return `há ${h} h`
  return `há ${inteiro.format(Math.round(h / 24))} dias`
}

/** Texto da tendencia em linguagem simples (voz do Farol): numero e sentido, nunca so seta. */
export function descreverTendencia(
  tendencia: string | null | undefined,
  taxaCmH: number | null | undefined,
  aceleracaoCmH2: number | null | undefined,
): string | null {
  if (!tendencia || taxaCmH == null) return null
  const modulo = inteiro.format(Math.abs(taxaCmH))
  if (tendencia === 'estavel') return 'Estável'
  const base =
    tendencia === 'subindo' ? `Subindo ${modulo} cm por hora` : `Descendo ${modulo} cm por hora`
  return tendencia === 'subindo' && (aceleracaoCmH2 ?? 0) >= 2 ? `${base} e acelerando` : base
}

export const nomeDaFonte = (codigo: string): string =>
  codigo.startsWith('dcsc') ? 'Defesa Civil de SC' : codigo
