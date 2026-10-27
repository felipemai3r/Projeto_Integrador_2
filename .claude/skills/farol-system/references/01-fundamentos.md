# Os 9 Fundamentos do Farol

Os Fundamentos são **a lei**. Os tokens materializam a lei e os componentes a implementam. Em dúvida visual, a resposta nasce aqui.

---

## 01 Cor
- **Três camadas:** primitivos (`--fa-prim-*`, paletas cruas) → semânticos (`--fa-color-*`, intenção) → modo noite (reescrita dos semânticos). O componente consome **só semânticos** e tokens de risco.
- **Paletas:** Ardósia (neutro frio), **Defesa** (azul institucional, ação e marca), **Sinal** (laranja da marca, só assinatura), Vale (verde), Maré (ciano, informação e chuva), Âmbar (amarelo), **Chama** (laranja de risco), Brasa (vermelho), **Trovão** (roxo). Cada uma tem passos 50 a 900.
- **Identidade Defesa Civil SC:** azul + laranja. O azul é a cor de **ação** (`--fa-color-action-primary`, Defesa 600, 6,5:1 com texto branco). O laranja **Sinal** é só **marca**: o filete do cabeçalho e o logotipo. Não é botão nem destaque de conteúdo, porque o laranja que o usuário lê como dado é o de **risco** (Chama, faixa Alerta da escala da Defesa Civil de SC), propositalmente mais fechado e avermelhado. A chamada principal da tela usa o azul de ação. Texto sobre Chama é sempre Ardósia 900.
- **Feedback de interface** (info, sucesso, aviso, perigo) é diferente de **risco hidrológico**. Não misture: um erro de formulário não usa a cor de "alerta" do rio.
- **Contraste:** todo par validado em WCAG AA (texto 4,5:1, componente 3:1). `scripts/verificar-contraste.py` precisa sair com 0 falhas.

## 02 Risco *(exclusivo do Farol)*
- A escala de risco é o produto. Cinco faixas, a escala de risco da Defesa Civil de SC, e dois estados de dado, todos em `--fa-risk-*` (o valor de dado usa sublinhado, `alerta_alto`; o token usa hífen, `--fa-risk-alerta-alto-*`):

| Token | Significado | Cor base | Ícone (Lucide) | Rótulo |
|---|---|---|---|---|
| `normal` | Abaixo de todos os limiares | Vale | `circle-check` | Normal |
| `atencao` | Atingiu o 1º limiar | Âmbar (amarelo) | `circle-alert` | Atenção |
| `alerta` | Atingiu o 2º limiar | Chama (laranja) | `triangle-alert` | Alerta |
| `alerta_alto` | Atingiu o 3º limiar, grande perigo | Brasa (vermelho) | `octagon-alert` | Alerta alto |
| `extremo` | Risco extremo, aja imediatamente. Só existe com cota cadastrada | Trovão (roxo) | `siren` | Aja imediatamente |
| `desatualizado` | Dado velho, fonte fora do ar (RN04) | Ardósia | `clock-alert` | Dado desatualizado |
| `indisponivel` | Sem leitura para a estação | Ardósia | `circle-off` | Indisponível |

- Cada faixa expõe `-solid`, `-on-solid`, `-surface`, `-border`, `-content`. **Solid** é para selo e faixa cheia, **surface/border/content** é para cartão suave.
- **Cor nunca sozinha.** Toda faixa = cor + ícone + rótulo. Vale para daltonismo, sol na tela e impressão em preto e branco.
- **Escala oficial:** verde, amarelo, laranja, vermelho e roxo, como na Defesa Civil de SC. A cota da faixa `extremo` ainda não foi cadastrada: sem limiar, nenhum nível é classificado como extremo e a faixa some das réguas e dos gráficos. Trocar a cor de uma faixa muda **uma linha** em `risk.css`.
- **Cada faixa tem forma de ícone própria** (círculo, triângulo, octógono, sirene): a diferença entre laranja e vermelho não pode depender só da cor.
- **Dado ≠ risco:** `desatualizado` e `indisponivel` são cinza de propósito. Um dado velho nunca pode parecer "normal" (verde) por engano.
- **Séries de gráfico** (`--fa-data-*`): observado = linha cheia Defesa; estimado = tracejada + faixa de incerteza; cenário hipotético = tracejada cinza-ardósia com selo (o laranja é de risco); chuva = barras Maré.

## 03 Tipografia
- **Atkinson Hyperlegible Next** é a única família. 3 pesos: 400, 500, 700.
- **Escala em 4 grupos:** Dado (56/40/24, o número do nível, tabular), Título (32 a 18, peso 700), Texto (18/16/14, peso 400, line-height 1,5 a 1,6), Rótulo (16/14/12, peso 500).
- Texto corrido nunca abaixo de 16px. 14px só como apoio. 12px só em rótulo curto.
- Número que muda ou se compara: `.fa-num` (algarismo tabular). Unidade colada com espaço fino: `4,62 m`.
- Cada token empacota **size + weight + line-height + tracking**; use o conjunto.

## 04 Espaçamento
- **Base 4px.** Todo valor é múltiplo de 4. Proibido `7px`, `13px`, `18px`.
- Três famílias com nome de papel: **inset** (dentro do componente, 4 a 24), **stack** (entre blocos, 8 a 48), **section** (entre seções, 32 a 96).
- **Alvo de toque mínimo 44px** (`--fa-target-min`), 48px para ação principal. Distância entre alvos adjacentes: 8px ou mais.

## 05 Forma
- **Âncora 10px.** Controle (botão, campo) 10, botão principal 14, card 14, modal 20, bottom sheet 28 no topo.
- **Pill (999px) só em chip e badge de status/risco** e trilha de switch. Nunca em botão, card, campo, imagem.
- Estrutura (divisor, tabela) não tem raio.

## 06 Elevação
- Sombra derivada da **Ardósia 900** (20, 31, 46), nunca preto puro (no modo noite a opacidade sobe para continuar legível).
- Em tela de risco, hierarquia vem de **cor e posição** antes de sombra. Sombra é reforço.
- **Z-index semântico**: `base, raised, sticky, dropdown, sheet, backdrop, modal, toast, emergency`. A faixa de alerta vigente usa `--fa-z-emergency` e fica acima de tudo.

## 07 Movimento
- **Centro 150ms, teto 400ms.** Entrada 160ms, saída 120ms (assimetria imutável).
- **Transição genérica de todas as propriedades não existe.** Declare `transition-property`.
- **Nada pisca.** Nenhum elemento alterna mais de 1 vez por segundo. Mudança de faixa de risco: no máximo um destaque único de 250ms, sem loop.
- `prefers-reduced-motion`: zera deslocamento, escala e animação.
- Indicador "ao vivo" é um ponto estático com o horário da leitura, não um pulso.

## 08 Grade e layout
- **Mobile-first.** Base 0 é o celular. Breakpoints `min-width`: 480 / 768 / 1024 / 1280.
- Colunas: 4 (celular), 8 (tablet), 12 (desktop). Gutter 16/24. Margem 16/32/40.
- Containers: `content` 1120 (padrão), `wide` 1280, `text` 680 (leitura), `narrow` 440 (formulário).
- **Risco na primeira dobra.** A faixa de risco das estações alvo aparece sem rolar a tela em 360×640. Qualquer informação de risco a no máximo 2 níveis de navegação (RNF08).
- Respeitar `env(safe-area-inset-*)` no PWA instalado.

## 09 Iconografia
- **Lucide** (`lucide-react`), traço 2px. Tamanhos: **16 / 20 / 24 / 40**. Padrão 20.
- O 40 é só para o ícone de faixa em destaque. Número direto é proibido; use `--fa-icon-size-*`.
- Ícone de risco é significado, nunca decoração. Ícone sozinho exige `aria-label`; ícone ao lado de texto leva `aria-hidden="true"`.

---

## Acessibilidade (transversal)
- Elemento nativo antes de `div` com `onClick`. Rótulo em todo campo e botão-ícone.
- Foco visível sempre (anel de 3px). Ordem de tabulação segue a ordem visual.
- Mudança de faixa de risco é anunciada: região `role="status"` (`aria-live="polite"`); alerta vigente usa `role="alert"` uma vez.
- Gráfico tem alternativa em texto/tabela (resumo + dados). Mapa tem lista equivalente.
- Zoom até 200% sem perda de função. Nenhuma informação só por cor.

## O selo Farol, checklist
- [ ] Zero cor solta: só `--fa-color-*` e `--fa-risk-*`.
- [ ] Toda faixa de risco com cor + ícone + rótulo.
- [ ] Laranja Sinal só no filete da marca. O laranja de dado é sempre a faixa Alerta (Chama), com ícone e rótulo.
- [ ] Medidas na escala de 4px; alvos de toque ≥ 44px.
- [ ] Pill só em chip/badge; raios da família certa.
- [ ] Atkinson, 400/500/700; números com `.fa-num`.
- [ ] Todo dado exibido tem fonte e horário; dado velho marcado.
- [ ] Observado, estimado e cenário distinguíveis sem cor.
- [ ] Aviso "fonte oficial: Defesa Civil" presente onde há risco ou previsão.
- [ ] Movimento 160/120ms, nada pisca, `prefers-reduced-motion` ok.
- [ ] Foco visível; teclado completo; `aria-*` correto.
- [ ] Modo noite verificado; 360px e 1280px verificados.
