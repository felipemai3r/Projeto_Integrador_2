# Frontend

PWA em React 19, TypeScript e Vite, com o design [Farol DS](../../.claude/skills/farol-system/SKILL.md).

## Estado

| Item | Situação |
|---|---|
| Tokens do Farol (`src/styles/farol.css`) | Em uso, modo dia e noite |
| Fonte Atkinson Hyperlegible Next | Empacotada (funciona offline) |
| Componentes | `RiskBadge`, `StationCard`, `LevelGauge`, `TrendIndicator`, `SourceStamp`, `StaleNotice`, `OfficialNotice`, `RainAccumulatedTable`, `Header`, `Skeleton` |
| Página | Painel (CDU01): situação dos rios alvo e chuva nos pontos a montante |
| PWA | Manifest, ícones e service worker que guarda só o casco (nunca `/api`) |
| Tipos da API | Gerados do OpenAPI (`src/lib/api-types.ts`) |

Tamanho: JavaScript de 86 kB comprimido na primeira tela (orçamento: 250 kB).

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
| `npm run tokens` | Copia `farol.css` da skill do design para `src/styles/` |
| `npm run api:types` | Regenera os tipos a partir de `http://localhost:8000/openapi.json` |

## Nota sobre o iCloud Drive

O repositório está dentro do iCloud Drive, que sincroniza e marca como ocultos os milhares de arquivos do `node_modules`. Depois de cada `npm install`, rode `npm run nosync`: ele move a pasta para `node_modules.nosync` (que o iCloud ignora) e deixa um link `node_modules`. Por causa do link, o `vite.config.ts` usa `resolve.preserveSymlinks: true`. Em Linux, no CI e fora do iCloud, nada disso é necessário.

## Regras

- Só tokens `--fa-*`. Nada de cor, espaço ou `z-index` literal fora de `src/styles/`.
- Todo risco com cor, ícone e texto. Todo dado com fonte e horário. Dado velho vira `desatualizado`.
- Componentes de domínio recebem `faixa` e `estado`, nunca cor.
- Detalhes em [padrão de desenvolvimento](../../docs/padrao-de-desenvolvimento.md#5-typescript-e-react).
