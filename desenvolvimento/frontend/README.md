# Frontend

PWA em React 19, TypeScript e Vite, com o design [Farol DS](../../.claude/skills/farol-system/SKILL.md).

## Estado

| Item | Situação |
|---|---|
| Tokens do Farol (`src/styles/farol.css`) | Em uso, modo dia e noite |
| Fonte Atkinson Hyperlegible Next | Empacotada (funciona offline) |
| Componentes | `RiskBadge`, `StationCard`, `LevelGauge`, `TrendIndicator`, `SourceStamp`, `StaleNotice`, `OfficialNotice`, `RainAccumulatedTable`, `Header`, `Skeleton` |
| Páginas | Painel, Previsão e simulador, Mapa, Registrar alagamento, Avisos (push), Como funciona, Qualidade dos dados, Relatório (imprime/PDF) e Moderação (login) |
| PWA | Manifest, ícones e service worker que guarda só o casco (nunca `/api`) |
| Tipos da API | Gerados do OpenAPI (`src/lib/api-types.ts`) |

Tamanho: cerca de 97 kB comprimidos na primeira tela (orçamento: 250 kB). Mapa, gráfico e formulários carregam sob demanda.

## Testes ponta a ponta

Rodam contra o sistema de verdade (banco, API, Nginx). O fluxo completo registra um alagamento, entra como moderador, valida, confere no mapa e **rejeita o registro de teste no fim** (fica só como rejeitado). Crie antes o usuário de teste (`docker compose exec api python -m api.criar_usuario ...`) e informe `E2E_EMAIL` e `E2E_SENHA`, ou use os valores de desenvolvimento do README do `desenvolvimento/`.

## Rodando

```bash
cd desenvolvimento/frontend
npm install
npm run nosync          # veja a nota abaixo
npm run dev             # http://localhost:5173, /api vai para http://localhost:8000
```

A API precisa estar no ar (`docker compose up` em `desenvolvimento/`).

| Comando | O que faz |
|---|---|
| `npm run dev` | Servidor de desenvolvimento |
| `npm run build` | Checa tipos e gera `dist/` com o service worker |
| `npm test` | Testes (Vitest e Testing Library) |
| `npm run lint` | ESLint com regras de acessibilidade (`jsx-a11y`) |
| `npm run e2e` | Testes ponta a ponta no Chrome do sistema (precisa do stack no ar; `E2E_URL` muda o endereço, padrão `http://localhost:8080`) |
| `npm run e2e:acessibilidade` | Varredura axe (WCAG A e AA) das 9 telas, em modo dia e noite |
| `npm run tokens` | Copia `farol.css` da skill do design para `src/styles/` |
| `npm run api:types` | Regenera os tipos a partir de `http://localhost:8000/openapi.json` |

## Nota sobre o iCloud Drive

O repositório está dentro do iCloud Drive, que sincroniza e marca como ocultos os milhares de arquivos do `node_modules`. Depois de cada `npm install`, rode `npm run nosync`: ele move a pasta para `node_modules.nosync` (que o iCloud ignora) e deixa um link `node_modules`. Por causa do link, o `vite.config.ts` usa `resolve.preserveSymlinks: true`. Em Linux, no CI e fora do iCloud, nada disso é necessário.

## Regras

- Só tokens `--fa-*`. Nada de cor, espaço ou `z-index` literal fora de `src/styles/`.
- Todo risco com cor, ícone e texto. Todo dado com fonte e horário. Dado velho vira `desatualizado`.
- Componentes de domínio recebem `faixa` e `estado`, nunca cor.
- Detalhes em [padrão de desenvolvimento](../../docs/padrao-de-desenvolvimento.md#5-typescript-e-react).
