/// <reference lib="webworker" />
// Service worker. Guarda APENAS o casco da aplicacao (HTML, JS, CSS, fonte, icones).
// Resposta de /api/* nunca e cacheada: dado ao vivo nao pode aparecer como se fosse atual.
// O push (Sprint 3) entra neste mesmo arquivo.
import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<string | { url: string; revision: string | null }>
}

precacheAndRoute(self.__WB_MANIFEST)
// Rotas do app (SPA) abrem o casco em cache, inclusive sem rede. /api nunca passa por aqui.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL('/index.html'), { denylist: [/^\/api\//] }),
)

// Notificacao push (CDU07). O texto vem pronto do servidor: titulo, corpo, url e tag.
interface DadosPush {
  titulo?: string
  corpo?: string
  url?: string
  tag?: string
}

self.addEventListener('push', (evento) => {
  let dados: DadosPush = {}
  try {
    dados = (evento.data?.json() ?? {}) as DadosPush
  } catch {
    dados = { corpo: evento.data?.text() }
  }
  evento.waitUntil(
    self.registration.showNotification(dados.titulo ?? 'Rios de Presidente Getúlio', {
      body: dados.corpo,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      tag: dados.tag, // mesma estacao substitui o aviso anterior, nao empilha
      data: { url: dados.url ?? '/' },
    }),
  )
})

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close()
  const url = (evento.notification.data as { url?: string } | null)?.url ?? '/'
  evento.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((janelas) => {
      const aberta = janelas.find((j) => 'focus' in j)
      return aberta ? aberta.focus() : self.clients.openWindow(url)
    }),
  )
})

self.addEventListener('install', () => void self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))
