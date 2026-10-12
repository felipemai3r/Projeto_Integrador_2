---
name: farol-system
description: Construir qualquer tela, componente ou protótipo do sistema de suporte à decisão para enchentes de Presidente Getúlio (SC) com o Farol Design System, a identidade visual inspirada na Defesa Civil de Santa Catarina (azul institucional, laranja de sinalização, escala de risco verde/ciano/amarelo/vermelho). Use sempre que for projetar ou codar UI do projeto (painel, previsão, simulação, mapa de ocorrências, inscrição de push, administração), criar componente React, escolher cor, tipografia, espaço, ícone ou texto de interface, ou garantir que algo "tem a cara do Farol". Carrega os 9 Fundamentos, os tokens CSS `--fa-*` e o catálogo de componentes React.
---

# farol-system, o construtor do Farol DS

O Farol é o sistema de design do projeto Presidente Getúlio. Nasceu do mesmo método do Arrow (Fundamentos, depois tokens, depois componentes, depois tela), mas **não é o Arrow**: tem identidade própria, prefixo `--fa-`, stack React, abordagem mobile-first e uma dimensão que o Arrow não tem, a **escala de risco**.

> **O que entregar:** UI que o morador entende em 3 segundos no celular, durante a chuva, e que o coordenador da Defesa Civil confia à meia-noite. Cada entrega sai com o **selo Farol**: tokens semânticos (nunca hex solto), risco sempre com ícone e texto, alvo de toque de 44px, modo noite funcionando, fonte e horário de todo dado.

## A hierarquia (a regra que rege tudo)

```
Fundamentos 01–09  →  Tokens (--fa-*)  →  Componentes (React)  →  A tela
(a lei, o porquê)     (a DNA em CSS)      (domínio + base)        (o que o usuário vê)
```

1. **A lei vem dos Fundamentos** (`references/01-fundamentos.md`). Dúvida de cor, tamanho, forma ou movimento: a resposta está lá.
2. **Nunca escreva valor solto.** Cor, espaço, raio, sombra, duração: sempre token (`var(--fa-color-action-primary)`, `var(--fa-space-inset-lg)`). Hex cru, `13px` mágico e `transition` genérica estão fora do padrão. Referência em `references/02-tokens.md`.
3. **Construa com os componentes do Farol**, não reinvente. Catálogo e contratos em `references/03-componentes.md`. Antes de codar um card de estação ou um selo de risco do zero, use o do catálogo.
4. **Selo = Definition of Done.** Só diga "está no padrão Farol" quando o checklist do fim de `01-fundamentos.md` passar e o resultado tiver sido visto renderizado.

## O que torna o Farol diferente (leia antes de construir)

| Aspecto | Farol | Por quê |
|---|---|---|
| Identidade | Azul Defesa (`defesa`) + laranja Sinal (`sinal`) | Remete à Defesa Civil de SC. O laranja é assinatura e **nunca** significa risco |
| Risco | Dimensão própria, `--fa-risk-*`, 4 faixas + 2 estados de dado | A informação central do produto. Espelha a escala oficial (RF32) |
| Fonte | Atkinson Hyperlegible Next | Desenhada para distinguir caracteres; o número do nível é o dado mais importante |
| Layout | Mobile-first, 4/8/12 colunas | Quem usa durante a chuva está no celular, com rede ruim |
| Modo noite | Obrigatório e automático | Consulta de madrugada é o caso de uso real |
| Movimento | Calmo, teto 400ms, nada pisca | Tela de risco não pode competir com a informação nem causar desconforto |
| Stack | React + TypeScript + CSS Modules | Segue `docs/arquitetura-desenvolvimento.md` |

## Fluxo de uso

### 1. Entenda o que vai construir
Tela de risco? Formulário? Mapa? Identifique quais Fundamentos pesam. Painel: Cor, **Risco**, Tipografia (dado), Grade. Formulário de ocorrência: Espaço, Forma, Movimento, Voz. Qualquer tela: Acessibilidade.

### 2. Puxe a DNA
- **No projeto (`web/`)**: copie `assets/farol.css` para `web/src/styles/farol.css` e importe uma vez em `main.tsx`. Instale a fonte (`npm i @fontsource-variable/atkinson-hyperlegible-next`) e importe-a no mesmo ponto. Os `var(--fa-*)` passam a existir em toda a aplicação.
- **Fora do projeto** (protótipo avulso): abra `assets/guia-visual.html` como referência e importe `assets/farol.css`.
- Para regenerar `farol.css` depois de editar `assets/tokens/*.css`: `bash .claude/skills/farol-system/scripts/build.sh`.
- Para conferir contraste depois de mexer em cor: `python3 .claude/skills/farol-system/scripts/verificar-contraste.py` (deve terminar com 0 falhas).

### 3. Construa com tokens e componentes
- Layout próprio usa só token: `padding: var(--fa-space-inset-lg)`, `border-radius: var(--fa-shape-surface-md)`, `color: var(--fa-color-content-primary)`.
- Tipografia por conjunto (`size + weight + line-height + tracking`), nunca só o tamanho. Número que muda usa `.fa-num` (algarismo tabular).
- Ícones: Lucide, 16/20/24/40. Ícone de risco é parte do significado.

### 4. Honre os inegociáveis (o selo)
- **Cor:** só semânticos `--fa-color-*` e `--fa-risk-*`. Nunca `--fa-prim-*` em componente, nunca hex.
- **Risco:** toda faixa aparece com **cor + ícone + rótulo de texto**. Cor sozinha é falha de acessibilidade.
- **Laranja Sinal** só em marca e destaque pontual (faixa do cabeçalho, CTA "Registrar ocorrência"). Nunca para indicar risco.
- **Dado sempre assinado:** todo número exibido carrega fonte e horário (`SourceStamp`, RNF16). Dado velho vira `desatualizado`, nunca some em silêncio (RN04).
- **Estimativa nunca parece observação:** observado = linha cheia, estimado = tracejada com faixa de incerteza, cenário = tracejada laranja com selo "cenário hipotético" (RN03, RF19).
- **Aviso oficial:** toda tela com risco ou previsão mostra que a fonte oficial é a Defesa Civil (RN09, RF33).
- **Espaço:** múltiplo de 4. Alvo de toque mínimo 44px.
- **Forma:** `pill` só em chip e badge de status, trilha de switch. Nunca em botão, card, campo.
- **Movimento:** entrada 160ms, saída 120ms, teto 400ms. Nada pisca. `prefers-reduced-motion` zera deslocamento.
- **Foco:** `:focus-visible` com anel de 3px, nunca removido. Elemento nativo antes de `div` clicável.
- **Modo noite:** vem dos tokens (`data-theme="dark"`, `.dark` ou preferência do sistema). Não hardcode cor por tema.

### 5. Valide antes de declarar pronto
- Renderize de verdade (navegador), em 360px de largura e em 1280px, nos modos dia e noite.
- `grep` de higiene no código novo: sem `#[0-9a-fA-F]{3,8}` fora de `tokens/`, sem `transition: all`, sem `z-index` numérico, sem `font-family` diferente da do token.
- Teste com o risco em cada uma das 4 faixas e nos estados `desatualizado` e `indisponivel`.

## A voz do Farol (texto de interface)

Português do Brasil, simples, sem jargão (RNF06). Quem lê pode estar assustado e com pressa.
- Frase curta. Verbo na ação: "Registrar alagamento", "Avisar quando subir", "Ver previsão".
- Explique o termo técnico onde ele aparece: "Nível do rio (altura da água em relação ao leito)". Evite "cota" sem explicação.
- Diga o que significa, não só o número: "4,62 m. Atenção: o rio está acima do nível que preocupa."
- Previsão é **estimativa**, nunca promessa. Escreva "pode subir", "estimamos", nunca "vai alagar".
- Nunca use tom alarmista (caixa alta, exclamação, "URGENTE"). A cor e o ícone já carregam a urgência.
- Todo aviso de risco termina com a fonte oficial: "Fonte oficial: Defesa Civil de Presidente Getúlio."
- Detalhes e modelos de texto em `references/04-padroes-de-tela.md`.

## Mapa dos arquivos
- `references/01-fundamentos.md`: os 9 Fundamentos (a lei) e o checklist do selo.
- `references/02-tokens.md`: todos os tokens semânticos por dimensão.
- `references/03-componentes.md`: catálogo React (base + domínio) com contratos de props.
- `references/04-padroes-de-tela.md`: composição das telas, estados obrigatórios, voz e acessibilidade.
- `assets/tokens/*.css`: fonte da DNA por dimensão. `assets/farol.css`: build de arquivo único.
- `assets/guia-visual.html`: guia visual navegável (paleta, risco, tipografia, componentes de exemplo).
- `scripts/build.sh` e `scripts/verificar-contraste.py`: geração do build e checagem WCAG AA.

## Princípio final
Liberdade para compor telas novas, desde que cada pixel saia da DNA. O Farol não é um tema aplicado por cima: é o que garante que a informação mais importante do sistema, o risco, seja lida do mesmo jeito por qualquer pessoa, em qualquer aparelho, a qualquer hora.
