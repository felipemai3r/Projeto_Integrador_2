/** Suporte e detalhes de Web Push no navegador. Funcoes puras onde possivel, para teste. */

export type SituacaoPush =
  | 'carregando'
  | 'nao-suportado'
  | 'iphone-sem-instalar'
  | 'negado'
  | 'sem-service-worker'
  | 'nao-inscrito'
  | 'inscrito'

export function ehIphone(agente: string): boolean {
  return /iPad|iPhone|iPod/.test(agente)
}

export function suportaPush(janela: { navigator: Navigator }): boolean {
  return 'serviceWorker' in janela.navigator && 'PushManager' in janela && 'Notification' in janela
}

/** No iPhone o push so existe no app instalado na tela inicial (iOS 16.4 ou superior). */
export function iphoneSemInstalar(agente: string, instalado: boolean): boolean {
  return ehIphone(agente) && !instalado
}

/** Chave publica VAPID (base64url) para Uint8Array, formato exigido pelo subscribe. */
export function chaveParaBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4))
    .replace(/-/g, '+')
    .replace(/_/g, '/')
  const bruto = atob(base64)
  const bytes = new Uint8Array(new ArrayBuffer(bruto.length))
  for (let i = 0; i < bruto.length; i++) bytes[i] = bruto.charCodeAt(i)
  return bytes
}

export function jaInstalado(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}
