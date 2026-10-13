# Análise do projeto e plano de ação

Documento interno da equipe. Resume a análise completa do repositório em 12/10/2026, os pontos que precisam de decisão antes de programar e o plano de desenvolvimento da Fase 3. Complementa [arquitetura-desenvolvimento.md](arquitetura-desenvolvimento.md) (como construir) e [padrao-de-desenvolvimento.md](padrao-de-desenvolvimento.md) (como escrever o código).

## Sumário

1. [Onde estamos](#1-onde-estamos)
2. [Pontos principais](#2-pontos-principais)
3. [Inconsistências encontradas na documentação](#3-inconsistências-encontradas-na-documentação)
4. [Lacunas técnicas a resolver antes de codar](#4-lacunas-técnicas-a-resolver-antes-de-codar)
5. [Decisões que dependem da equipe](#5-decisões-que-dependem-da-equipe)
6. [Plano de ação](#6-plano-de-ação)
7. [Corte de escopo se o tempo apertar](#7-corte-de-escopo-se-o-tempo-apertar)
8. [Padrões do projeto](#8-padrões-do-projeto)

---

## 1. Onde estamos

| Item | Situação |
|---|---|
| Fase 1 e Fase 2 (levantamento, RADIAN, especificação) | Concluídas e documentadas |
| Validação da especificação | Pendências PE01 a PE10 abertas, nenhuma respondida no repositório |
| Código | **Nenhum.** O repositório tem só documentação. Fase 3 não começou |
| Coleta de dados | **Não está rodando.** Cada dia sem coleta é dado perdido |
| Design e padrão de código | Definidos neste ciclo: [Farol DS](../.claude/skills/farol-system/SKILL.md) e [padrão de desenvolvimento](padrao-de-desenvolvimento.md) |

### 1.1 Andamento em 13/10/2026

| Etapa do plano | Situação |
|---|---|
| Sprint 0: esqueleto, banco, `ingestor`, carga inicial, CI | Concluído. Falta a decisão D1 (máquina 24h) e o backup diário |
| Sprint 1: adaptadores de barragem e Open-Meteo, `api` (estações, série, chuva, risco), painel e PWA | Concluído, exceto `AlertBanner` e o painel de qualidade |
| Sprint 2: correlação defasada e endpoint `/api/correlacao` | Concluído ([ADR 0003](adr/0003-correlacao-defasada-primeiros-resultados.md)). Falta a página "Como funciona" no front e o gráfico de histórico |
| Sprints 3 a 5 | Não iniciados |

Dados da coleta real: série de 5 minutos a partir de 22/07/2026 (21 dias já se haviam perdido), cerca de 23 mil leituras por estação, 416 mil horas de chuva ERA5 desde nov/2020. A estação do Revólver continua sem dado público.

## 2. Pontos principais

### 2.1 O que está forte

- Problema real, com demanda vinda do coordenador da Defesa Civil, e lacunas honestas frente ao painel municipal (seção 3 da especificação).
- Escopo cortado com critério: a mancha de inundação saiu porque o dado não existe, e o registro participativo entra no lugar.
- Honestidade analítica: baselines obrigatórios, critério de publicação (RN07) e limitação declarada (seção 9.5). Prometer acurácia sem dados seria o maior risco de credibilidade.
- Arquitetura simples e proporcional: três serviços Python, PostgreSQL, PWA, sem fila, sem TimescaleDB.
- Rastreabilidade RF, CDU e RADIAN, útil para a banca.

### 2.2 O que é urgente

**1. A janela de 80 dias da API REST está andando.** A validação foi em 19/09. Pelos cálculos da própria especificação, o histórico acessível naquele dia começava por volta de 1º/07. Hoje (12/10) o começo da janela está perto de 24/07, ou seja, **cerca de 21 dias de série de 5 minutos já se perderam** (medido: a série disponível começa em 22/07/2026) e mais um dia some a cada dia. A coleta (etapas 2 e 3 do roteiro) é a tarefa mais importante e não depende de nenhuma decisão pendente.

**2. A coleta precisa rodar 24 horas por dia.** Um notebook que dorme cria lacunas e invalida a análise de correlação. É preciso uma máquina sempre ligada: servidor da UDESC (ainda sem confirmação), VPS barato ou equipamento da equipe que não desligue. Essa escolha bloqueia o início real da coleta (decisão D1).

**3. Pedidos institucionais têm prazo fora do nosso controle** e custam um e-mail: ANA (PE09), Defesa Civil de SC para o histórico (PE10), Defesa Civil municipal para limiares, estações de serra e lista de eventos (PE05 a PE08). Devem sair esta semana, antes de qualquer linha de código.

### 2.3 Riscos de maior impacto

| Risco | Por que importa | Resposta |
|---|---|---|
| Modelo sem dado suficiente (RI01, RI03) | 80 dias, poucos ou nenhum evento extremo | Entregar o pipeline, a correlação defasada e a avaliação honesta. A correlação é o resultado científico principal do semestre |
| Estação do Revólver (DCSC-00174) **sem série pública** | Está no inventário mas não retorna histórico (fontes-de-dados, seção 8). A segunda estação alvo só terá tempo real | Tratar como estação "apenas observada" no painel; modelo e correlação começam pelo Rio dos Índios; PE06 |
| GraphQL só aceita operação registrada, REST em domínio DDNS (`mks-unifique.ddns.net`) | Pode mudar ou sumir sem aviso | Adaptador isolado, canário diário de contrato, `bruto` em JSONB para reprocessar |
| Push no iOS | Web Push no iPhone só funciona com o app instalado na tela inicial (iOS 16.4 ou superior) | Orientar instalação na tela de inscrição; documentar como limitação RE06 |
| Alerta falso | Destrói a confiança em um produto de segurança | RN02, RN03, RN04, RN07 já cobrem; adicionar histerese (seção 4) |
| Equipe de duas pessoas | Escopo grande (3 serviços, PWA, mapa, push, modelo) | Roteiro enxuto, corte de escopo pré-definido (seção 7), revisão cruzada de PR |

## 3. Inconsistências encontradas na documentação

Corrigir antes da validação com o professor.

| # | Onde | Problema | Correção sugerida |
|---|---|---|---|
| I1 (corrigido em 13/10) | Especificação 4.4 (rastreabilidade) | Intervalos de RF desatualizados: cita RF15 a RF19 como painel, RF20 a RF23 como registro, RF24 a RF27 como alerta e RF28 a RF32 como administração. Os RF reais são: análise RF09 a RF15, painel RF16 a RF21, registro RF22 a RF27, alerta RF28 a RF33, administração RF34 a RF39 | Reescrever a tabela com os intervalos da seção 6 |
| I2 | `Rascunhos` (não versionado) | Tem requisitos que **não estão na especificação**: classificação por chuva (50 mm em 24h observação, 60 mm alerta) e escala de 3 cores (verde, amarelo, vermelho) | Decidir se vira regra de negócio (D3) e versionar ou apagar o arquivo |
| I3 | Especificação 8 e RN01 | Escala de 4 faixas (normal, observação, atenção, alerta), mas o rascunho cita 3 cores | Mapeamento de cor proposto no Farol DS (observação em ciano), a validar com a Defesa Civil (PE05) |
| I4 (resolvido: sem PostGIS, ADR 0001) | Arquitetura seção 1 e `docker-compose.yml` de referência | Texto cita PostGIS, mas a imagem é `postgres:16-alpine`, que não tem PostGIS | Usar `postgis/postgis:16-3.4` ou assumir latitude e longitude simples e checar o município por polígono na aplicação |
| I5 | Arquitetura seção 2, CDU11 passo 8 | O `ingestor` "não calcula risco" e a `api` só reage a requisição, mas o CDU11 manda reavaliar o risco a cada leitura nova. **Ninguém dispara a reavaliação** | Criar o job `avaliador` (seção 4, item 1) |
| I6 | Arquitetura seção 10 | O serviço `web` sobe na porta 5173 (servidor de desenvolvimento do Vite) e a seção 13 usa o mesmo compose em produção | Build estático servido pelo Nginx em produção; Vite só em `docker-compose.override.yml` |
| I7 | Especificação 10 | São 15 casos de uso, só 8 estão expandidos (CDU01, 02, 03, 04, 07, 09, 11, 13) | Aceitável para a entrega; expandir CDU05, 06, 08, 10, 12 durante a implementação |
| I8 | Roteiro (arquitetura, seção 14) | Alerta e push (etapa 11) ficam depois do modelo, mas o alerta por nível **observado** não precisa de modelo | Antecipar o alerta por observação (plano, sprint 3) |

## 4. Lacunas técnicas a resolver antes de codar

1. **Quem reavalia o risco e dispara alerta.** Proposta: job `avaliador` no serviço `api` (APScheduler, a cada minuto) que lê a última leitura válida de cada estação alvo, classifica, compara com a faixa vigente e cria o `alerta`. Garantir **uma única instância** (lock no banco com `pg_advisory_lock`) para não enviar push duplicado.
2. **Histerese de faixa.** Sem ela, um nível oscilando em torno de 4,50 m gera alerta de entrada e saída repetidos. Regra: para voltar a uma faixa menos grave, o nível precisa ficar abaixo do limiar por 3 leituras consecutivas ou 15 minutos. Registrar como RN10.
3. **Regra de chuva do rascunho.** Se confirmada, vira um segundo gatilho: acumulado de 24h em um ponto de influência (50 mm observação, 60 mm alerta). Exige RN nova, tabela `limiar_chuva` e ajuste do CDU10. Decisão D3.
4. **Polígono do município** para o E1 do CDU04 ("ponto fora do município"). Obter da malha do IBGE (a skill `brasilapi` e a API de malhas do IBGE servem) e guardar como GeoJSON simplificado na aplicação.
5. **Usuários de moderação.** `ADMIN_USER` único não atende a Defesa Civil moderando. Criar tabela `usuario` mínima (nome, e-mail, papel `admin` ou `moderador`, hash de senha) e registrar autor em cada moderação (RF26, RF38).
6. **Foto de ocorrência (LGPD).** Remover metadados EXIF (inclui GPS e modelo do aparelho), limitar tamanho (5 MB), converter para JPEG redimensionado, guardar fora do banco. Limitar envios por dispositivo (RI05) com limite por IP e por token anônimo.
7. **Fuso horário.** Banco e API em UTC; apresentação em America/Sao_Paulo. Os formatos de data das fontes têm offset (`-0300`); normalizar na entrada.
8. **Cache e dado ao vivo no PWA.** Confirmado na arquitetura: service worker só guarda o casco, nunca resposta de dado.
9. **Segredos e VAPID.** Gerar uma vez, guardar fora do repositório, documentar rotação.
10. **Backup.** `pg_dump` diário para fora da máquina desde a primeira semana. A base é o único ativo que não se reconstitui.

## 5. Decisões que dependem da equipe

| ID | Decisão | Recomendação | Bloqueia |
|---|---|---|---|
| D1 | Onde roda a coleta 24h até o servidor da UDESC existir | VPS pequeno (custo baixo) ou máquina da UDESC, o que estiver disponível primeiro. O `docker compose` é portátil e migra depois | Sprint 0 |
| D2 | Cor das faixas de risco | Verde, ciano, amarelo, vermelho (proposta do Farol). Validar com a Defesa Civil | Telas finais |
| D3 | Gatilho por chuva (50 e 60 mm em 24h) entra no escopo? | Entra como **indicador informativo** no painel agora e como gatilho de alerta só depois de confirmado com a Defesa Civil | Etapa de alerta |
| D4 | Papéis de moderação | Dois papéis, `admin` (equipe) e `moderador` (Defesa Civil) | Etapa de moderação |
| D5 | Domínio e HTTPS do portal | Subdomínio UDESC se houver; senão domínio próprio com Let's Encrypt. Push exige HTTPS | Etapa de push |
| D6 | Licença do repositório | Definir (MIT ou equivalente) antes de abrir | Publicação |

## 6. Plano de ação

Sprints semanais. O calendário das aulas após o item 16 não está no repositório; **ajustar as datas ao plano de ensino**. A ordem é o que importa: coleta primeiro, valor visível cedo, núcleo analítico no meio, notificação por último.

Legenda de prioridade: O obrigatório, I importante, D desejável (MoSCoW da especificação).

### Sprint 0, 12 a 18/10: parar a perda de dados

| Entrega | Detalhe | Critério de pronto |
|---|---|---|
| Pedidos institucionais enviados | PE09 (ANA), PE10 (DCSC), PE05 a PE08 (município) | E-mails enviados, protocolo anotado |
| Esqueleto do repositório | Estrutura da seção 3 da arquitetura, `docker-compose.yml`, `.env.example`, `.gitignore`, CI mínimo (lint e teste) | `docker compose up` sobe `db` e `api` vazia |
| Banco e `common` | Migrações Alembic de `fonte`, `estacao`, `leitura`, `log_coleta`; seed das 8 estações | `alembic upgrade head` e seed rodam do zero |
| `ingestor` com GraphQL | Adaptador `Tags_data`, normalização, plausibilidade (RF07), log (RF35), agendador de 5 minutos | Leituras novas a cada 5 minutos com log de sucesso |
| **Carga inicial REST** | Baixar os dias ainda disponíveis para todas as estações | Contagem de leituras por estação conferida contra o esperado |
| **Deploy em máquina 24h** | Decisão D1 executada | Coleta rodando sem intervenção por 48h |
| Backup diário | `pg_dump` agendado, cópia fora da máquina | Arquivo restaurado com sucesso uma vez |

### Sprint 1, 19 a 25/10: primeira tela útil

| Entrega | Prioridade |
|---|---|
| Adaptadores de barragem e Open-Meteo (previsão e archive ERA5) com carga do histórico longo de chuva (RF04, RF05, RF08) | O |
| Job de lacunas via REST a cada 30 minutos; canário diário de contrato | O |
| `api`: `/estacoes`, `/estacoes/{codigo}/atual`, `/serie`, `/chuva/acumulada`; `risco.py` com limiares e taxa e aceleração (RF09, RF10) | O |
| Seed de limiares oficiais (RN01) com autor e justificativa | O |
| `web`: projeto Vite, tokens do Farol, fonte, `Header`, `StationCard`, `RiskBadge`, `SourceStamp`, `StaleNotice`; página Painel (CDU01); `manifest` e service worker de casco | O |
| Testes unitários de risco, normalização e plausibilidade | O |

Marco: **Painel público no ar** com nível, faixa, tendência e fonte (critério de aceitação 1).

### Sprint 2, 26/10 a 1º/11: análise e gráficos

| Entrega | Prioridade |
|---|---|
| `SeriesChart`, `RainAccumulatedTable`, seletor de período (RF17, RF18) | O |
| `modelo`: `features.py` sem vazamento temporal, `correlacao.py` com defasagem de 1 a 36 h (RF13, estágio 1) | O |
| Endpoint `/correlacao` e página "Como funciona" com o resultado, em linguagem simples | O |
| `/qualidade` e painel de qualidade de dados (RF36) | I |
| Teste de não vazamento temporal | O |

Marco: **primeiro resultado analítico** (tempo de resposta de cada ponto de influência), citável no artigo.

### Sprint 3, 2 a 8/11: ocorrências e alertas por observação

| Entrega | Prioridade |
|---|---|
| Autenticação, tabela `usuario`, papéis (D4, RF37) | O |
| Registro de ocorrência: formulário, mapa Leaflet, foto sem EXIF, associação das condições hidrológicas (CDU04, RF22 a RF24) | O |
| Mapa de ocorrências e moderação com histórico (CDU05, CDU08, RF25, RF26) | O |
| Job `avaliador`, histerese, `alerta` por nível **observado** (CDU07, RN02 a RN04) | O |
| Inscrição, VAPID, `pywebpush`, service worker de push (CDU06, RF29 a RF31, RF39) | O |
| `AlertBanner` e `OfficialNotice` | O |

Marco: **notificação push chega ao aparelho** em transição de faixa observada (critério 7) e ocorrências aparecem no mapa depois de moderadas (critério 6).

### Sprint 4, 9 a 15/11: previsão e simulação

| Entrega | Prioridade |
|---|---|
| Treino Ridge por horizonte, validação walk-forward, baselines de persistência e tendência, registro de modelo (estágio 2) | O |
| Critério de publicação RN07 aplicado de ponta a ponta (previsão indisponível com motivo) | O |
| `/previsao` e `/simulacao`; telas Previsão e Simulação com `ScenarioForm` (CDU02, CDU03, CDU09, RF11, RF12, RF14, RF19) | O |
| Alerta por **previsão**, com rótulo (RN03) | I |
| LightGBM, comparado ao Ridge (estágio 3) | D |

Marco: critérios 4 e 5 atendidos, ou a previsão fica documentada como indisponível por dado insuficiente, com a análise de correlação como entrega.

### Sprint 5, 16 a 22/11: fechamento e publicação

| Entrega | Prioridade |
|---|---|
| Build de produção, Nginx, HTTPS, publicação no servidor (RNF13, itens 25 e 26) | O |
| Testes ponta a ponta (registro de ocorrência, inscrição e push) | O |
| Revisão de acessibilidade (teclado, VoiceOver, 360 px, modo noite, zoom 200%) | O |
| Relatório PDF (CDU15, RF21) | I |
| Dados e figuras para o artigo da Fase 4; atualização da documentação e do README | O |
| Teste com a Defesa Civil municipal e ajuste do que ela apontar | O |

### Dependências críticas

```
Sprint 0 (coleta) ──► Sprint 2 (correlação) ──► Sprint 4 (modelo)
        │                                           ▲
        └─► Sprint 1 (API + painel) ──► Sprint 3 (alertas, push, ocorrências)
PE05 (limiares)  ──► telas finais e alerta        PE07 (eventos) ──► avaliação do modelo
```

## 7. Corte de escopo se o tempo apertar

Cortar nesta ordem, sem comprometer os critérios de aceitação:

1. RF15 (processamento de boletins não estruturados), já desejável.
2. Estágio 3 (LightGBM).
3. RF21 (relatório PDF).
4. RF23 (foto de ocorrência).
5. Alerta por previsão (manter só o observado).
6. RF05 (barragem como variável), se o adaptador der trabalho.

Nunca cortar: coleta contínua, painel com fonte e horário, correlação defasada, registro de ocorrência com moderação, alerta e push por observação, aviso de que não é alerta oficial.

## 8. Padrões do projeto

| Padrão | Onde | Conteúdo |
|---|---|---|
| Design | [`.claude/skills/farol-system`](../.claude/skills/farol-system/SKILL.md) | Farol DS: 9 fundamentos, tokens `--fa-*`, componentes React, voz, acessibilidade. Guia visual em `assets/guia-visual.html` |
| Desenvolvimento | [padrao-de-desenvolvimento.md](padrao-de-desenvolvimento.md) | Git, commits, Python, TypeScript, API, testes, CI, segurança, definição de pronto |
| Arquitetura | [arquitetura-desenvolvimento.md](arquitetura-desenvolvimento.md) | Serviços, banco, contêineres, roteiro |

Para usar o design em uma conversa com o Claude Code, invoque a skill `farol-system` (por exemplo `/farol-system monte a tela do Painel`).
