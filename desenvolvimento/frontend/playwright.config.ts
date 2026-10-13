import { defineConfig } from '@playwright/test'

// Testes ponta a ponta contra o stack rodando (dev em :5173 ou producao em :8080).
// Usa o Chrome instalado no sistema (channel 'chrome'), sem baixar navegador.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_URL ?? 'http://localhost:8080',
    channel: 'chrome',
    viewport: { width: 390, height: 844 },
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
  },
})
