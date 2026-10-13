import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import {
  chaveParaBytes,
  iphoneSemInstalar,
  jaInstalado,
  suportaPush,
  type SituacaoPush,
} from '../lib/push'

const ESPERA_SW_MS = 4000

async function registro(): Promise<ServiceWorkerRegistration | null> {
  const pronto = navigator.serviceWorker.ready
  const tempo = new Promise<null>((r) => setTimeout(() => r(null), ESPERA_SW_MS))
  return Promise.race([pronto, tempo])
}

/** Estado e acoes dos avisos por push (CDU06). */
export function usePush() {
  const [situacao, setSituacao] = useState<SituacaoPush>('carregando')
  const [erro, setErro] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    let vivo = true
    async function descobrir() {
      if (iphoneSemInstalar(navigator.userAgent, jaInstalado())) return 'iphone-sem-instalar'
      if (!suportaPush(window)) return 'nao-suportado'
      if (Notification.permission === 'denied') return 'negado'
      const reg = await registro()
      if (!reg) return 'sem-service-worker'
      return (await reg.pushManager.getSubscription()) ? 'inscrito' : 'nao-inscrito'
    }
    descobrir()
      .then((s) => vivo && setSituacao(s))
      .catch(() => vivo && setSituacao('nao-suportado'))
    return () => {
      vivo = false
    }
  }, [])

  const inscrever = useCallback(async (estacao: string | null, faixaMinima: string) => {
    setErro(null)
    setOcupado(true)
    try {
      const chave = await api.pushChave()
      if (!chave.configurado) {
        setErro('Os avisos ainda não estão ativos neste servidor.')
        return
      }
      const permissao = await Notification.requestPermission()
      if (permissao !== 'granted') {
        setSituacao(permissao === 'denied' ? 'negado' : 'nao-inscrito')
        return
      }
      const reg = await registro()
      if (!reg) {
        setSituacao('sem-service-worker')
        return
      }
      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: chaveParaBytes(chave.chave_publica),
        }))
      const json = sub.toJSON()
      await api.inscrever({
        endpoint: sub.endpoint,
        keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
        estacao,
        faixa_minima: faixaMinima,
      })
      setSituacao('inscrito')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não conseguimos ativar os avisos agora.')
    } finally {
      setOcupado(false)
    }
  }, [])

  const cancelar = useCallback(async () => {
    setErro(null)
    setOcupado(true)
    try {
      const reg = await registro()
      const sub = await reg?.pushManager.getSubscription()
      if (sub) {
        await api.cancelarInscricao(sub.endpoint)
        await sub.unsubscribe()
      }
      setSituacao('nao-inscrito')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não conseguimos cancelar agora. Tente de novo.')
    } finally {
      setOcupado(false)
    }
  }, [])

  return { situacao, erro, ocupado, inscrever, cancelar }
}
