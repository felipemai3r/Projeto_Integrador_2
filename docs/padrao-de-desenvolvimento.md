# Padrão de desenvolvimento

Regras de escrita e de processo do código do projeto. Vale para os dois membros da equipe e para qualquer ferramenta de apoio (incluindo o Claude Code). Em conflito entre este documento e o hábito pessoal, vale o documento; para mudar uma regra, altere o documento em um PR.

Documentos relacionados: [arquitetura-desenvolvimento.md](arquitetura-desenvolvimento.md) (o que construir), [plano-de-acao.md](plano-de-acao.md) (quando), [Farol DS](../.claude/skills/farol-system/SKILL.md) (como a interface parece).

## Sumário

1. [Princípios](#1-princípios)
2. [Idioma e nomes](#2-idioma-e-nomes)
3. [Git e revisão](#3-git-e-revisão)
4. [Python](#4-python)
5. [TypeScript e React](#5-typescript-e-react)
6. [CSS e design](#6-css-e-design)
7. [API](#7-api)
8. [Banco de dados](#8-banco-de-dados)
9. [Testes](#9-testes)
10. [Segurança, privacidade e segredos](#10-segurança-privacidade-e-segredos)
11. [Observabilidade e operação](#11-observabilidade-e-operação)
12. [Documentação](#12-documentação)
13. [Definição de pronto](#13-definição-de-pronto)
14. [Automação (CI e ganchos)](#14-automação-ci-e-ganchos)

---

## 1. Princípios

1. **Segurança antes de elegância.** É um sistema que pode influenciar decisão de sair de casa. Dado errado apresentado como certo é o pior defeito possível. Na dúvida, mostrar "indisponível" é melhor que mostrar um número duvidoso.
2. **Dado sempre rastreável.** Todo valor tem fonte, estação e horário da medição (RNF16). Guardamos o payload bruto.
3. **Falhar com graça.** Fonte fora do ar não derruba o sistema (RNF04, RNF05). Mantém o último dado válido, marca como desatualizado e registra.
4. **Simples e proporcional.** Sem fila, sem microserviço extra, sem abstração sem segundo uso. Duas pessoas precisam entender tudo.
5. **Reproduzível.** Um comando sobe o sistema (RNF12). Nada depende da máquina de alguém.
6. **Estimativa nunca se passa por observação.** Vale no código (campo `origem`), na API e na tela.

## 2. Idioma e nomes

Seguem o que a [arquitetura](arquitetura-desenvolvimento.md) já adotou.

| Elemento | Regra | Exemplo |
|---|---|---|
| Domínio (tabelas, colunas, funções, variáveis, tipos, rotas) | Português, sem acento, `snake_case` em Python, SQL e JSON | `leitura`, `medido_em`, `classificar_faixa` |
| Termos técnicos consagrados | Inglês, quando traduzir piora | `adapter` vira `Adaptador` por já estar no documento; `payload`, `token`, `scheduler` ficam |
| TypeScript | Domínio em português, `camelCase` para variáveis e funções, `PascalCase` para tipos e componentes | `nivelM`, `EstacaoAtual`, `StationCard` |
| Componentes React | Nome em inglês, como no catálogo do Farol (`StationCard`, `RiskBadge`) | ver [catálogo](../.claude/skills/farol-system/references/03-componentes.md) |
| Arquivos Python | `snake_case.py` | `dcsc_graphql.py` |
| Arquivos TypeScript | Componente em `PascalCase.tsx`; demais em `camelCase.ts` | `StationCard.tsx`, `api.ts` |
| Unidade no nome | Sempre que o tipo não carrega a unidade | `nivel_m`, `chuva_mm`, `taxa_cm_h`, `duracao_ms`, `frequencia_s` |
| Faixas de risco | Valores fixos: `normal`, `observacao`, `atencao`, `alerta` (sem acento) | enum único em `common` e espelhado no front |
| Origem do dado | `observado`, `previsto`, `cenario` | |
| Textos para o usuário | Português do Brasil, com acento, na voz do Farol | ver [padrões de tela](../.claude/skills/farol-system/references/04-padroes-de-tela.md) |
| Comentários e docstrings | Português, explicam o **porquê** (regra de negócio, armadilha da fonte), não o quê | |

Códigos de requisito entram em comentário só quando a regra não é óbvia: `# RN04: dado desatualizado não gera alerta`.

## 3. Git e revisão

### 3.1 Fluxo
- `main` é sempre implantável. **Sem commit direto em `main`** depois do Sprint 0 (no Sprint 0, commits diretos são aceitos para montar o esqueleto).
- Trabalho em ramos curtos, de 1 a 3 dias: `feat/ingestor-graphql`, `fix/plausibilidade-nivel`, `docs/plano-de-acao`, `chore/ci`.
- Todo ramo vira **Pull Request** revisado **pela outra pessoa** da equipe. Autor não aprova o próprio PR.
- Merge por **squash**, com a mensagem final no padrão abaixo.
- PR pequeno: idealmente menos de 400 linhas alteradas fora de migração e arquivo gerado.

### 3.2 Mensagens de commit
Formato: `tipo(escopo): descrição no imperativo, em português, sem ponto final`.

| Tipo | Uso |
|---|---|
| `feat` | Funcionalidade nova |
| `fix` | Correção de defeito |
| `docs` | Documentação |
| `test` | Testes |
| `refactor` | Mudança sem alterar comportamento |
| `chore` | Build, CI, dependências, configuração |
| `style` | Formatação sem efeito de lógica |

Escopos: `ingestor`, `modelo`, `api`, `web`, `db`, `common`, `infra`, `docs`, `design`.

Exemplos: `feat(ingestor): adiciona adaptador do GraphQL da Defesa Civil`, `fix(api): impede alerta com leitura desatualizada`. Mensagens do histórico de documentação (ASCII, sem prefixo) permanecem como estão; a regra vale daqui para frente.

### 3.3 Descrição do PR
Modelo: **O que muda** · **Por quê** (requisito ou caso de uso: RF/RN/CDU) · **Como testar** · **Capturas de tela** (mudança visual, celular e desktop, dia e noite) · **Riscos**.

### 3.4 Revisão
Quem revisa confere: comportamento correto e casos de borda, teste que falharia se o código estivesse errado, ausência de segredo, aderência a este padrão e ao Farol, impacto em migração e em dado já coletado.

### 3.5 Versionamento
Tags `v0.N.0` por marco de sprint. Migração de banco nunca é editada depois de mesclada: cria-se outra.

## 4. Python

- **Versão:** 3.12. Gerenciamento por `pyproject.toml` por serviço; `uv` ou `pip` com `requirements` travado.
- **Formatação e lint:** `ruff format` e `ruff check` (regras `E, F, I, B, UP, SIM, PL, DTZ`). Linha de 100 colunas.
- **Tipos:** anotação em toda função pública. `mypy --strict` em `common`, `api` e no núcleo de `modelo` (`features`, `validacao`); `mypy` padrão no resto.
- **Datas:** sempre com fuso (`datetime` *aware*, UTC). Regra do Ruff `DTZ` ligada. Nunca `datetime.now()` sem fuso nem `utcnow()`.
- **Contratos:** entradas e saídas de borda com **Pydantic**. Nada de `dict` solto atravessando serviço.
- **Banco:** SQLAlchemy 2.0 (estilo `select()`), sessões por requisição ou por job, sem SQL concatenado com string. Migração só por Alembic.
- **Adaptadores** (`ingestor/adapters`): implementam a interface `Adaptador`; não conhecem o banco; não lançam exceção de rede para fora sem converter para um erro do domínio; têm teste de contrato com resposta gravada.
- **Erros:** exceções específicas do domínio (`FonteIndisponivel`, `ContratoQuebrado`, `LeituraImplausivel`). Nunca `except Exception: pass`. Quem captura registra log com contexto.
- **Funções puras primeiro:** classificação por limiar, tendência, plausibilidade, montagem de variáveis são funções puras e testáveis sem banco.
- **Modelo estatístico:**
  - Janela de agregação usa **somente dado passado** em relação a `t`; há teste que prova.
  - Partição temporal *walk-forward*, jamais embaralhar.
  - Toda avaliação compara com **persistência** e **extrapolação linear**; o relatório registra os três.
  - Semente fixa (`random_state`) e versão dos dados gravada em `modelo.metadados`.
  - Artefato `joblib` com hash; só carregar artefato gerado por nós.
- **Concorrência:** jobs idempotentes (reexecutar não duplica; `UNIQUE` e `ON CONFLICT DO NOTHING` na ingestão). Job de avaliação com lock de banco (`pg_advisory_lock`).
- **Configuração:** somente por variável de ambiente lida em `common.config` (Pydantic Settings). Sem `os.environ` espalhado.

## 5. TypeScript e React

- **Stack:** React 18, Vite, TypeScript `strict`, React Router, TanStack Query para dados do servidor, Recharts, Leaflet, Radix UI para comportamento acessível.
- **Lint e formato:** ESLint (`@typescript-eslint`, `react-hooks`, `jsx-a11y`) e Prettier. `no-explicit-any` como erro.
- **Tipos da API:** gerados a partir do OpenAPI do FastAPI (`openapi-typescript`) em `web/src/lib/api-types.ts`. Não escrever tipo de resposta à mão; assim o contrato não diverge.
- **Dados:** toda chamada passa por `lib/api.ts` e por hooks do TanStack Query; componente não chama `fetch`. Tratar sempre os quatro estados: carregando, dado, desatualizado/indisponível, erro.
- **Componentes:** função, props tipadas, sem estado global para dado de servidor. Um componente por pasta (`Nome/Nome.tsx`, `.module.css`, `.test.tsx`, `index.ts`). Componentes de domínio recebem `faixa` e `estado`, nunca cor.
- **Acessibilidade:** regras `jsx-a11y` como erro. Elemento nativo antes de `div`. Rótulo em controle. Foco visível. Ver checklist do Farol.
- **Datas:** `Intl.DateTimeFormat` com `America/Sao_Paulo`; nunca formatar à mão. Números com `Intl.NumberFormat('pt-BR')` (vírgula decimal).
- **PWA:** service worker guarda **apenas o casco**; requisições `/api/*` usam `NetworkOnly`. Dado ao vivo nunca vem do cache.
- **Sem dependências à toa:** antes de instalar um pacote, conferir manutenção, tamanho e se uma API do navegador resolve. Meta: carregamento útil em 3 s em 4G (RNF01); orçamento de 250 kB de JavaScript comprimido na primeira tela.

## 6. CSS e design

- **Só tokens do Farol**: cor, espaço, raio, sombra, duração, z-index, fonte, tamanho de ícone vêm de `var(--fa-*)`. O Farol é a fonte de verdade ([SKILL.md](../.claude/skills/farol-system/SKILL.md)).
- **CSS Modules** por componente. Sem estilo inline, exceto valor realmente dinâmico (posição de marcador).
- **Proibido** fora de `tokens/`: cor hexadecimal ou `rgb()` literal, `z-index` numérico, `transition: all`, `font-family` próprio, medida fora da escala de 4 px, `!important`.
- **Mobile-first:** estilo base é o celular; `@media (min-width: …)` acrescenta.
- **Risco:** toda faixa com cor + ícone + texto. Laranja Sinal nunca indica risco.
- **Verificação automática:** `stylelint` com `color-no-hex`, `declaration-property-value-disallowed-list` (`transition: all`, `z-index` numérico) e `declaration-strict-value` para `color`, `background`, `border-color`, exceto em `tokens/`.
- **Tokens:** editou cor? Rode `bash .claude/skills/farol-system/scripts/verificar-contraste.py`; precisa terminar com 0 falhas. Regenerar o agregado com `scripts/build.sh`.

## 7. API

- **REST JSON**, FastAPI, OpenAPI automático em `/docs`. Rotas em português, no plural, conforme a [tabela da arquitetura](arquitetura-desenvolvimento.md#7-api).
- **Campos em `snake_case`**, datas em **ISO 8601 com offset** (`2026-10-12T14:35:00-03:00`), números em unidade SI com unidade no nome (`nivel_m`).
- **Metadados obrigatórios** em todo dado externo: `fonte`, `estacao`, `medido_em` (RNF16). Em toda previsão: `modelo_id`, `treinado_em`, `incerteza_m`, `origem`.
- **Estado do dado explícito:** `estado` com `ok`, `desatualizado` ou `indisponivel`. Nunca omitir silenciosamente.
- **Erros** no formato `{ "tipo": "...", "titulo": "...", "detalhe": "...", "campos": [...] }`, com código HTTP correto; mensagem para humano em português, sem *stack trace*.
- **Idempotência:** `POST` público (ocorrência, inscrição) tolera repetição por chave de idempotência ou por `UNIQUE`.
- **Limite de requisição** nas rotas públicas de escrita (RI05) e **CORS** restrito à origem do front.
- **Autenticação:** rotas `/api/admin/*` e moderação exigem token; papéis `admin` e `moderador`; todo acesso administrativo registra autor (RNF10).
- **Compatibilidade:** não remover nem renomear campo sem atualizar o front no mesmo PR. O tipo gerado do front acusa quebra.

## 8. Banco de dados

- Esquema da [arquitetura](arquitetura-desenvolvimento.md#4-modelo-físico-de-dados) é a referência; mudanças só por migração Alembic, revisada.
- Toda tabela de fato tem chave natural com `UNIQUE` para impedir duplicidade; índice composto onde há consulta de série (`estacao_id, variavel, medido_em DESC`).
- `TIMESTAMPTZ` sempre. Texto de domínio controlado por `CHECK` ou enum.
- `leitura.bruto` guarda o payload original; reprocessar é permitido, apagar não.
- Dados pessoais mínimos (RNF15): inscrição de push guarda só `endpoint` e chaves; ocorrência não guarda identificação do autor.
- **Backup diário** (`pg_dump`) com cópia externa e **teste de restauração** a cada marco.

## 9. Testes

| Tipo | Cobertura mínima | Ferramenta |
|---|---|---|
| Unitário | Funções puras: risco, tendência, plausibilidade, normalização, histerese | pytest, vitest |
| Contrato dos adaptadores | Cada adaptador contra resposta real gravada (`tests/fixtures/*.json`) | pytest |
| Canário de contrato | Job diário compara a estrutura da fonte real com a esperada e avisa | job no `ingestor` |
| Integração | API contra PostgreSQL de teste com dado semeado | pytest, testcontainers |
| Modelo | Sem vazamento temporal; baseline calculado; critério RN07 | pytest |
| Componentes | 4 faixas, desatualizado, indisponível, modo noite | vitest, Testing Library |
| Ponta a ponta | Registrar ocorrência; inscrever e receber push | Playwright |
| Acessibilidade | `axe` automatizado nas telas principais, mais roteiro manual | `@axe-core/playwright` |

Regras:
- Teste novo para todo defeito corrigido, que **falha sem a correção**.
- Código crítico (classificação de risco, plausibilidade, histerese, critério de publicação, montagem de variáveis) com **cobertura de ramos acima de 90%**. No restante, cobertura é consequência, não meta.
- Sem teste que dependa de rede real, relógio real ou ordem de execução. Relógio injetável.
- Sem `skip` ou `xfail` sem comentário com o motivo e o prazo.

## 10. Segurança, privacidade e segredos

- `.env` no `.gitignore`. **Nenhuma credencial no repositório**, nem em exemplo, comentário, teste ou histórico (RNF09). Se vazar, rotacionar na hora.
- `.env.example` só com nomes e valores de exemplo inofensivos.
- Dependências: lockfile versionado, atualização mensal, `pip-audit` e `npm audit` no CI.
- Entrada de usuário validada no servidor (Pydantic), mesmo que o front valide. Saída escapada pelo React; proibido `dangerouslySetInnerHTML`.
- Upload: tipo e tamanho validados, EXIF removido, nome gerado pelo servidor, servido por rota própria com `Content-Disposition` adequado.
- Cabeçalhos de segurança no Nginx (HSTS, `X-Content-Type-Options`, CSP restritiva).
- Credenciais de terceiros (ANA) só no servidor; o front nunca as vê.
- LGPD: coletar o mínimo, ocorrência anônima, exclusão de inscrição pelo usuário (RF39), política de privacidade em linguagem simples no portal.

## 11. Observabilidade e operação

- **Logs estruturados em JSON** (`logging` com formatador JSON), nível por variável de ambiente, sempre com `fonte`, `estacao` e `correlacao_id` quando houver. Sem dado pessoal em log.
- **Health checks:** `/api/saude` (processo vivo) e `/api/qualidade` (cobertura por estação, lacunas, última coleta, fontes instáveis).
- **Alerta interno da equipe:** se a coleta ficar mais de 15 minutos sem leitura nova, avisar (e-mail ou mensagem). O primeiro sintoma de problema grave é silêncio.
- **Execução:** `docker compose`, `restart: unless-stopped`, volumes nomeados, versão das imagens fixada (sem `latest`).

## 12. Documentação

- Decisão arquitetural relevante vira **ADR** curto em `docs/adr/NNNN-titulo.md` (contexto, decisão, consequências). Exemplos já pendentes: polígono do município, histerese, avaliador.
- Mudança de requisito, regra de negócio ou caso de uso atualiza a [especificação](especificacao-completa.md) **no mesmo PR** e mantém a rastreabilidade.
- README de cada serviço: como rodar, variáveis, comandos.
- Texto em português, direto, sem jargão desnecessário. Tabelas para dados comparáveis. Sem emojis.

## 13. Definição de pronto

Um item só está pronto quando:

- [ ] Atende o requisito ou caso de uso referenciado, com o fluxo alternativo e de exceção relevantes.
- [ ] Tem teste automatizado; CI verde (lint, tipos, testes, build, build do Docker).
- [ ] Revisado e aprovado pela outra pessoa.
- [ ] Interface: verificada em 360 px e 1280 px, modo dia e noite, com teclado; selo Farol cumprido.
- [ ] Dado exibido tem fonte e horário; estados desatualizado e indisponível tratados.
- [ ] Sem segredo, sem `console.log`, sem código morto, sem TODO sem dono.
- [ ] Migração (se houver) testada do zero e sobre dado existente.
- [ ] Documentação e rastreabilidade atualizadas.
- [ ] Rodou com `docker compose up` em uma máquina limpa (ao final de cada sprint).

## 14. Automação (CI e ganchos)

**Ganchos locais** (`pre-commit`): `ruff`, `ruff format`, `prettier`, `eslint`, `stylelint`, detecção de segredo (`gitleaks`), bloqueio de arquivo grande e de `.env`.

**CI** (GitHub Actions) em todo PR:

1. Python: `ruff`, `mypy`, `pytest` (com PostgreSQL de serviço), `pip-audit`.
2. Web: `eslint`, `stylelint`, `tsc --noEmit`, `vitest`, `npm audit`, `vite build` com verificação do orçamento de tamanho.
3. Design: `python3 .claude/skills/farol-system/scripts/verificar-contraste.py`.
4. Geração de tipos da API e verificação de que o arquivo commitado está atualizado.
5. `docker compose build`.
6. Ponta a ponta (Playwright) no ramo `main` e antes de cada marco.

**Canário de contrato** das fontes roda como job agendado no servidor, não no CI.
