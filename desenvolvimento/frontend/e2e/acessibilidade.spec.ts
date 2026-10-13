import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

// Regras WCAG 2.x A e AA. So falha em violacao "serious" ou "critical".
const PAGINAS = [
  ['Painel', '/'],
  ['Previsão', '/previsao'],
  ['Mapa', '/mapa'],
  ['Registrar', '/registrar'],
  ['Avisos', '/avisos'],
  ['Como funciona', '/como-funciona'],
  ['Qualidade', '/qualidade'],
  ['Relatório', '/relatorio'],
  ['Moderação (login)', '/moderacao'],
] as const

for (const esquema of ['light', 'dark'] as const) {
  for (const [nome, rota] of PAGINAS) {
    test(`acessibilidade: ${nome} (${esquema})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: esquema })
      await page.goto(rota)
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(1500) // graficos e mapa carregam sob demanda
      const resultado = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .exclude('.leaflet-container') // tiles e controles do Leaflet sao de terceiros
        .analyze()
      const graves = resultado.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))
      expect(
        graves.map((v) => `${v.id}: ${v.help} (${v.nodes.length} elementos, ex.: ${v.nodes[0]?.target.join(' ')})`),
      ).toEqual([])
    })
  }
}
