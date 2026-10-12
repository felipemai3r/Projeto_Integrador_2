# Referência de tokens (a DNA do Farol)

Tokens **semânticos**, os que você consome. Vêm prontos ao importar `assets/farol.css`. Valores abaixo são do modo dia; o modo noite reescreve os mesmos nomes.

---

## Cor (`--fa-color-*`)

### Superfície
| Token | Dia | Noite |
|---|---|---|
| `surface-base` | #FFFFFF | #141F2E |
| `surface-subtle` | #F3F5F7 | #273445 |
| `surface-raised` | #E3E7ED | #3D4A5C |
| `surface-inverted` | #141F2E | #F3F5F7 |
| `surface-brand` | #063265 | #051F3D |
| `surface-scrim` | 56% Ardósia 900 | 64% preto |

### Conteúdo (texto e ícone)
| Token | Dia | Noite | Uso |
|---|---|---|---|
| `content-primary` | #141F2E | #F3F5F7 | Texto principal, dado |
| `content-secondary` | #3D4A5C | #C9D0D9 | Texto de apoio |
| `content-tertiary` | #515F70 | #A9B3C1 | Metadado (horário, fonte) |
| `content-disabled` | #8894A5 | #677689 | Desabilitado |
| `content-inverted` | #FFFFFF | #141F2E | Sobre superfície invertida |
| `content-link` | #055BBD | #81B2E9 | Link |
| `content-on-brand` | #FFFFFF | #FFFFFF | Sobre `surface-brand` |

### Borda
`border-subtle` · `border-default` (#C9D0D9, divisor) · `border-strong` (#8894A5, contorno de campo, 3:1) · `border-focus` (#055BBD)

### Ação (azul Defesa)
`action-primary` #055BBD · `action-hover` #064893 · `action-pressed` #063265 · `action-on` #FFFFFF (texto sobre ação) · `action-subtle` #D6E7FA · `action-surface` #EDF4FD · `action-disabled` #C9D0D9

### Destaque de marca (laranja Sinal)
`accent` #F68128 · `accent-hover` #FAA361 · `accent-pressed` #D5630B · `accent-on` #141F2E (texto escuro sobre o laranja). **Uso pontual, nunca risco.**

### Feedback de interface
Famílias `info`, `success`, `warning`, `danger`, cada uma com `-surface`, `-border`, `-content`. Não são faixas de risco.

### Estado
`state-hover-neutral` · `state-hover-action` · `state-focus-ring` (#0A70E6, anel 3px) · `state-disabled-surface` · `state-disabled-content`

### Marca
`brand-marinho` #063265 · `brand-sinal` #F68128

---

## Risco (`--fa-risk-*`)

Faixas: `normal` · `observacao` · `atencao` · `alerta`. Estados de dado: `desatualizado` · `indisponivel`. Cada uma com 5 tokens.

| Faixa | `-solid` | `-on-solid` | `-surface` | `-border` | `-content` |
|---|---|---|---|---|---|
| normal | #188644 | #FFFFFF | #DDF3E6 | #188644 | #095327 |
| observacao | #036C8C | #FFFFFF | #D8F0F8 | #036C8C | #045067 |
| atencao | #F9C824 | #141F2E | #FEF3CD | #8F6D00 | #664E00 |
| alerta | #B4190E | #FFFFFF | #FDD6D3 | #B4190E | #680903 |
| desatualizado | #515F70 | #FFFFFF | #E3E7ED | #677689 | #273445 |
| indisponivel | #3D4A5C | #FFFFFF | #F3F5F7 | #677689 | #3D4A5C |

Séries de dado: `--fa-data-observed` · `-forecast` · `-uncertainty` · `-scenario` · `-rain` · `-grid`.

---

## Tipografia (`--fa-type-*`, `--fa-font-*`)
- Família: `--fa-font-family-base` (Atkinson Hyperlegible Next). Pesos: `--fa-font-weight-regular` 400 · `-medium` 500 · `-bold` 700.
- Cada variante tem `-size`, `-weight`, `-line-height`, `-tracking`.

| Grupo | Variantes (tamanho) |
|---|---|
| Dado | `dado-xl` 56 · `dado-lg` 40 · `dado-md` 24 (700, tabular) |
| Título | `titulo-xl` 32 · `titulo-lg` 24 · `titulo-md` 20 · `titulo-sm` 18 (700) |
| Texto | `texto-lg` 18 · `texto-md` 16 · `texto-sm` 14 (400) |
| Rótulo | `rotulo-lg` 16 · `rotulo-md` 14 · `rotulo-sm` 12 (500) |

Aplicação em CSS:
```css
font: var(--fa-type-titulo-lg-weight) var(--fa-type-titulo-lg-size)/var(--fa-type-titulo-lg-line-height) var(--fa-font-family-base);
letter-spacing: var(--fa-type-titulo-lg-tracking);
```
Classe `.fa-num` para algarismo tabular.

---

## Espaçamento (`--fa-space-*`), base 4px
- **inset** (dentro): `xs` 4 · `sm` 8 · `md` 12 · `lg` 16 · `xl` 24
- **stack** (entre blocos): `xs` 8 · `sm` 16 · `md` 24 · `lg` 32 · `xl` 48
- **section** (entre seções): `sm` 32 · `md` 48 · `lg` 64 · `xl` 96
- Alvo de toque: `--fa-target-min` 44 · `--fa-target-comfortable` 48

## Forma (`--fa-shape-*`), âncora 10px
- **control:** `sm` 6 (checkbox) · `md` 10 (botão, campo) · `lg` 14 (botão principal) · `pill` (switch)
- **surface:** `sm` 10 (tooltip, menu) · `md` 14 (card, painel, aviso) · `lg` 20 (modal) · `sheet` 28 (topo do bottom sheet)
- **status:** `sm` 4 (tag em tabela) · `pill` (chip e badge de risco)
- **structure:** `none` 0 · `sm` 4 (progresso, skeleton)

## Elevação (`--fa-elevation-*`, `--fa-shadow-*`, `--fa-z-*`)
- Sombras `--fa-shadow-0…4`. Semânticos: `flat`, `card`, `card-hover`, `control-pressed`, `header`, `dropdown`, `sheet`, `modal`, `toast`.
- Z-index: `base` 0 · `raised` 10 · `sticky` 200 · `dropdown` 300 · `sheet` 400 · `backdrop` 450 · `modal` 500 · `toast` 600 · `emergency` 700.

## Movimento (`--fa-motion-*`, `--fa-easing-*`)
- `fast` 100 (hover, press) · `base` 160 (entrada) · `exit` 120 (saída) · `highlight` 250 (dado novo, 1 vez) · `sheet` 250 · `ceiling` 400.
- Easings: `standard`, `enter`, `exit`.
- Classes: `.fa-motion-hover`, `-press`, `-enter`, `-exit`, `-highlight`. Todas neutralizadas em `prefers-reduced-motion`.

## Grade (`--fa-grid-*`, `--fa-bp-*`, `--fa-container-*`)
- Colunas `sm` 4 · `md` 8 · `lg` 12. Gutter 16/24/24. Margem 16/32/40.
- Breakpoints (mobile-first, `min-width`): `sm` 480 · `md` 768 · `lg` 1024 · `xl` 1280. *Variável CSS não funciona dentro de `@media`: use os números.*
- Containers: `content` 1120 · `wide` 1280 · `text` 680 · `narrow` 440. Classe `.fa-container`.
- `--fa-safe-top` / `--fa-safe-bottom` para entalhe e barra de gestos.

## Iconografia (`--fa-icon-*`)
- Tamanhos: `compact` 16 · `default` 20 · `comfortable` 24 · `prominent` 40. Traço `--fa-icon-stroke` 2.
- Cores: `primary` · `secondary` · `action` · `inverted` · `danger` · `success`.
