import { expect, test } from '@playwright/test'

const EMAIL = process.env.E2E_EMAIL ?? 'moderador@local.dev'
const SENHA = process.env.E2E_SENHA ?? 'teste-local-2026'

test('painel mostra o rio, a faixa de risco e a fonte oficial, sem erro no console', async ({ page }) => {
  const erros: string[] = []
  page.on('console', (m) => m.type() === 'error' && erros.push(m.text()))
  page.on('pageerror', (e) => erros.push(String(e)))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Situação dos rios agora' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Rio dos Índios' })).toBeVisible()
  await expect(page.getByText(/Fonte: Defesa Civil de SC/).first()).toBeVisible()
  await expect(page.getByText(/A fonte oficial é a Defesa Civil/)).toBeVisible()
  expect(erros).toEqual([])
})

test('sem rolagem horizontal em celular nas telas principais', async ({ page }) => {
  for (const rota of ['/', '/previsao', '/mapa', '/registrar', '/avisos', '/como-funciona']) {
    await page.goto(rota)
    await page.waitForTimeout(800)
    const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
    expect(larguras[0], rota).toBeLessThanOrEqual(larguras[1]!)
  }
})

test('previsao sem modelo publicado diz que nao esta disponivel e por que', async ({ page }) => {
  await page.goto('/previsao')
  await expect(page.getByText(/A previsão ainda não está disponível/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Simular' })).toBeVisible()
})

test('ciclo completo: registrar alagamento, moderar, aparecer no mapa e ser retirado', async ({ page }) => {
  const nota = `e2e ${Date.now()}`
  // 1) cidadao registra, sem login
  await page.goto('/registrar')
  const mapa = page.getByRole('region', { name: /Mapa para marcar/ })
  await expect(mapa).toBeVisible()
  await page.waitForTimeout(1500)
  await mapa.locator('.leaflet-container').click({ position: { x: 150, y: 150 } })
  await page.getByRole('radio', { name: /Água na calçada/ }).check({ force: true })
  await page.getByLabel(/Descrição/).fill(nota)
  await page.getByRole('button', { name: 'Enviar registro' }).click()
  // o clique pode cair fora do municipio: o servidor recusa com mensagem clara
  const resultado = page.getByText('Obrigado!').or(page.getByText(/dentro de Presidente Getúlio/))
  await expect(resultado).toBeVisible()
  test.skip(await page.getByText(/dentro de Presidente Getúlio/).isVisible(), 'ponto clicado fora do municipio')
  await expect(page.getByText('199')).toBeVisible()

  // 2) nao aparece no mapa publico enquanto pendente
  await page.goto('/mapa')
  await expect(page.getByText(nota)).toHaveCount(0)

  // 3) moderador entra e valida
  await page.goto('/moderacao')
  await page.getByLabel('E-mail').fill(EMAIL)
  await page.getByLabel('Senha').fill(SENHA)
  await page.getByRole('button', { name: 'Entrar' }).click()
  const cartao = page.getByRole('listitem').filter({ hasText: nota })
  await expect(cartao).toBeVisible()
  await cartao.getByRole('button', { name: 'Validar' }).click()
  await expect(cartao).toHaveCount(0)

  // 4) agora aparece no mapa publico
  await page.goto('/mapa')
  await expect(page.getByText(nota).first()).toBeVisible()

  // 5) limpeza: devolve o estado ao anterior (rejeita o registro de teste)
  const token = await page.evaluate(async ([e, s]) => {
    const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) })
    return ((await r.json()) as { token: string }).token
  }, [EMAIL, SENHA])
  const lista = await page.evaluate(async () => (await (await fetch('/api/ocorrencias')).json()) as { id: number; descricao: string | null }[])
  const alvo = lista.find((o) => o.descricao === nota)
  expect(alvo).toBeDefined()
  const rej = await page.request.patch(`/api/ocorrencias/${alvo!.id}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { acao: 'rejeitar', nota: 'registro de teste automatizado' },
  })
  expect(rej.ok()).toBeTruthy()
})

test('login errado nao entra e nao revela detalhes', async ({ page }) => {
  await page.goto('/moderacao')
  await page.getByLabel('E-mail').fill('ninguem@exemplo.br')
  await page.getByLabel('Senha').fill('senha-errada-123')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('alert')).toHaveText('E-mail ou senha incorretos.')
})

test('navegacao por teclado chega ao conteudo e o foco fica visivel', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')
  const foco = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    if (!el) return null
    const estilo = getComputedStyle(el)
    return { tag: el.tagName, contorno: estilo.outlineStyle !== 'none' && parseFloat(estilo.outlineWidth) >= 2 }
  })
  expect(foco?.tag).toBeTruthy()
  expect(foco?.contorno).toBe(true)
})
