# Catálogo de componentes do Farol (React + TypeScript)

Local no projeto: `web/src/components/`. Um componente por pasta: `Nome/Nome.tsx`, `Nome.module.css`, `Nome.test.tsx`, `index.ts`. Estilo em **CSS Modules consumindo só `--fa-*`**. Sem biblioteca de UI de terceiros para o que está neste catálogo; para comportamento complexo e acessível (dialog, tooltip, tabs) usar **Radix UI primitives** e estilizar com os tokens.

Status: **contrato definido**, implementação acontece nas etapas do [plano de ação](../../../../docs/plano-de-acao.md). Este arquivo é a especificação que o código deve seguir.

Tipos compartilhados:
```ts
type Faixa = 'normal' | 'observacao' | 'atencao' | 'alerta'
type EstadoDado = 'ok' | 'desatualizado' | 'indisponivel'
type Origem = 'observado' | 'previsto' | 'cenario'
```

---

## A. Componentes de domínio (a alma do produto)

### RiskBadge
Selo de faixa de risco. Sempre cor + ícone + texto.

| Prop | Valores | Default |
|---|---|---|
| `faixa` | `Faixa` \| `'desatualizado'` \| `'indisponivel'` | obrigatório |
| `size` | `sm` \| `md` \| `lg` | `md` |
| `variant` | `solid` \| `soft` | `solid` |
| `origem` | `Origem` | `observado` (se `previsto`, exibe "Previsão" ao lado) |

Forma `pill`. Ícone da faixa (ver Fundamento 02). `aria-label` completo: "Risco: atenção, observado". Em `lg`, ícone de 24px.

### StationCard
Cartão de situação de uma estação alvo (CDU01). O elemento mais importante da tela inicial.

Conteúdo, nesta ordem: nome do curso d'água · `RiskBadge` · nível em `dado-xl` com unidade · `TrendIndicator` · `LevelGauge` · `SourceStamp`.

| Prop | Tipo |
|---|---|
| `estacao` | `{ codigo, nome, cursoDagua }` |
| `nivelM` | `number \| null` |
| `faixa` | `Faixa \| null` |
| `estado` | `EstadoDado` |
| `taxaCmH`, `aceleracaoCmH2` | `number \| null` |
| `medidoEm` | `string` (ISO 8601) |
| `fonte` | `string` |

Estado `desatualizado`: o nível continua visível, com `StaleNotice` no topo e `RiskBadge` em cinza. Estado `indisponivel`: sem número, mensagem "Sem leitura desta estação" (CDU01 E2). Superfície `surface-md`, borda esquerda de 4px na cor `-border` da faixa.

### LevelGauge
Régua vertical (ou horizontal em `compact`) do nível do rio com os três limiares (RN01) e o marcador atual.

Props: `nivelM`, `limiares: { observacao, atencao, alerta }`, `maxM`, `orientacao`. Faixas pintadas com `-surface` e linhas de limiar com `-border` e rótulo em metros ("4,50 m"). Marcador com seta e valor. Alternativa em texto obrigatória (`role="img"` + `aria-label`: "Nível 4,62 metros, entre atenção e alerta").

### TrendIndicator
Tendência do nível: ícone + texto + taxa. `subindo` (`trending-up`), `estavel` (`minus`), `descendo` (`trending-down`). Texto: "Subindo 12 cm por hora". Sinal de aceleração opcional ("e acelerando"). Nunca depende só da seta.

### RainAccumulatedTable
Chuva acumulada por ponto de influência nas janelas 1h, 3h, 6h, 12h, 24h, 48h, 72h (RF17). Tabela semântica (`<table>`), colunas de janela, números `.fa-num` alinhados à direita. Destaca em `observacao`/`atencao` quando passa dos limiares de chuva configurados. No celular vira lista de cartões, um por ponto.

### SeriesChart
Gráfico de série temporal (Recharts) para nível e previsão (RF18, RF19).

Props: `observado[]`, `estimado[]?`, `incertezaFaixa?`, `limiares`, `periodo`, `origem`. Regras: observado = linha cheia `--fa-data-observed`; estimado = tracejada `--fa-data-forecast` + faixa `--fa-data-uncertainty`; cenário = tracejada `--fa-data-scenario` + selo "Cenário hipotético". Linhas horizontais dos limiares com rótulo. Linha vertical "agora". Tooltip e **tabela alternativa** em `<details>`. Seletor de período como `SegmentedControl`. Sem animação de entrada.

### SourceStamp
Linha de proveniência: "Fonte: Defesa Civil de SC · estação DCSC-00043 · medido às 14:35". Atende RF20 e RNF16. `rotulo-sm`, `content-tertiary`, ícone `database` 16px. Horário relativo + absoluto no `title`.

### StaleNotice
Aviso de dado desatualizado (RN04). `role="status"`. Texto: "Dado desatualizado. Última leitura boa às 13:10. Não é possível confirmar a situação agora." Cores `--fa-risk-desatualizado-*`. Nunca some sozinho.

### AlertBanner
Faixa de alerta vigente, fixa no topo, `--fa-z-emergency`. Mostra faixa, estação, origem (`observado` ou `previsto`), horário e link "Ver situação". Usa `-solid` da faixa. `role="alert"` apenas na primeira renderização; atualizações via `role="status"`. Não pisca. Pode ser dispensado só para faixas `observacao`; `atencao` e `alerta` permanecem enquanto vigentes.

### OfficialNotice
Rodapé de aviso (RN09, RF33): "Estimativa de apoio. A fonte oficial é a Defesa Civil de Presidente Getúlio." Obrigatório em Painel, Previsão e Simulação e em todo alerta/push. `info-surface`, ícone `info`.

### ScenarioForm
Formulário da simulação (CDU03): um `Field` numérico por ponto de influência (mm), janela de tempo, "Simular". Pré-preenchido com a previsão. Validação inline com mensagem humana ("Digite um valor entre 0 e 300 mm"). Resultado lado a lado: **Agora** × **Cenário**, com `RiskBadge` de cada um e selo "Cenário hipotético". Aviso de extrapolação (CDU03 E2) em `warning`.

### OccurrenceForm e OccurrenceMarker
`OccurrenceForm` (CDU04): passos curtos, ponto no mapa ou "usar minha localização", data/hora com "agora", tipo de impacto (4 opções com ícone), foto e descrição opcionais. `OccurrenceMarker` no mapa: ícone por tipo, cor por **status de moderação** (pendente, validada) com forma distinta, nunca só cor. Popup com tipo, data, e condições hidrológicas do momento.

### PushOptIn
Inscrição de notificação (CDU06): escolher estação e faixa mínima, explicar o que será enviado, botão "Avisar quando subir", cancelar a qualquer momento. Explica antes de pedir a permissão do navegador. iOS: orienta a instalar o app na tela inicial.

### DataQualityTable e ModerationQueue (administração)
Densidade maior permitida (única exceção ao modo arejado), mantendo alvo de toque no celular. `DataQualityTable`: cobertura por estação, lacunas, última coleta, fonte `instável`. `ModerationQueue`: lista de ocorrências pendentes com mapa, foto, condição hidrológica e ações Validar, Reclassificar, Rejeitar com registro de autor.

---

## B. Componentes base

| Componente | Notas de contrato |
|---|---|
| `Button` | `variant` `primary`\|`secondary`\|`ghost`; `tone` `action`\|`danger`; `size` `md`(44px)\|`lg`(48px, raio 14); `loading`, `block`, `leading`/`trailing`. `accent` (laranja, texto escuro) permitido **uma vez por tela** |
| `IconButton` | `label` obrigatório (`aria-label`); 44×44 mínimo |
| `Field` + `Input` / `Textarea` / `Select` | `label` visível sempre (placeholder não é rótulo), `hint`, `error` (texto + ícone, `role="alert"`), `required`. Altura 44px, borda `border-strong` |
| `Checkbox`, `Radio`, `Switch` | Área clicável de 44px incluindo o rótulo |
| `SegmentedControl` | Seleção de período do gráfico (1h, 6h, 24h, 72h); `role="tablist"`/radiogroup conforme uso |
| `Tabs` | Radix. Navegação principal no celular é **barra inferior** com 4 destinos: Painel, Previsão, Mapa, Avisos |
| `Sheet` / `Dialog` | Radix. Bottom sheet no celular (raio superior 28), modal no desktop. Foco preso, `Esc` fecha |
| `Toast` | `role="status"`; some em 6s, exceto erro. Posição acima da barra inferior |
| `Tooltip` | Só complemento; nada essencial dentro dele (não existe hover no celular) |
| `Skeleton` | Cor `surface-raised`, sem shimmer animado |
| `Icon` | Wrapper do Lucide com `size` 16/20/24/40 e `label` opcional |
| `Header` | Faixa de marca: fundo `surface-brand`, filete inferior laranja `brand-sinal` de 4px, nome do sistema, alternador de tema |
| `Text` | `variant` das escalas dado/titulo/texto/rotulo; `as` para a tag semântica correta |

## Regras de composição
- Um componente de domínio nunca recebe cor por prop: recebe `faixa`/`estado` e resolve internamente pelos tokens.
- Nenhum componente importa `--fa-prim-*`.
- Todo componente tem story/teste cobrindo: 4 faixas, `desatualizado`, `indisponivel`, modo noite, 360px.
