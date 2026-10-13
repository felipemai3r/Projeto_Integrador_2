/// <reference lib="webworker" />
// Service worker. Guarda APENAS o casco da aplicacao (HTML, JS, CSS, fonte, icones).
// Resposta de /api/* nunca e cacheada: dado ao vivo nao pode aparecer como se fosse atual.
// O push (Sprint 3) entra neste mesmo arquivo.
import { precacheAndRoute } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<string | { url: string; revision: string | null }>
}

precacheAndRoute(self.__WB_MANIFEST)

self.addEventListener('install', () => void self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))
