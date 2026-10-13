import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectManifest: { globPatterns: ['**/*.{js,css,html,svg,png,woff2}'] },
      manifest: {
        name: 'Rios de Presidente Getúlio',
        short_name: 'Rios PG',
        description:
          'Nível dos rios e chuva em Presidente Getúlio. Estimativa de apoio. A fonte oficial é a Defesa Civil.',
        lang: 'pt-BR',
        display: 'standalone',
        start_url: '/',
        theme_color: '#063265',
        background_color: '#ffffff',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  // node_modules e um link para node_modules.nosync (fora do iCloud); sem isto o Vite nao pre-empacota
  resolve: { preserveSymlinks: true },
  server: {
    port: 5173,
    // sem isto o Vite observa node_modules.nosync e entra em loop de recarga
    watch: { ignored: ['**/node_modules.nosync/**', '**/node_modules/**'] },
    proxy: { '/api': process.env.VITE_API_PROXY ?? 'http://localhost:8000' },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    css: false,
  },
})
