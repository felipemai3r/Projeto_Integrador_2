# Fontes de Dados: levantamento e validação técnica

Documento de apoio à [especificação completa](especificacao-completa.md). Registra o que foi testado, o que funciona, o que não funciona e o que depende de terceiros.

**Data da validação: 19/09/2026.** Todos os endpoints abaixo foram chamados de verdade nesta data, a partir de um navegador, e os resultados citados são os retornos reais. O que não foi testado está marcado como não testado.

## Sumário

1. [Resumo executivo](#1-resumo-executivo)
2. [Estações relevantes para Presidente Getúlio](#2-estações-relevantes-para-presidente-getúlio)
3. [Defesa Civil de SC, plataforma atual (GraphQL)](#3-defesa-civil-de-sc-plataforma-atual-graphql)
4. [Defesa Civil de SC, API REST anterior](#4-defesa-civil-de-sc-api-rest-anterior)
5. [Open-Meteo](#5-open-meteo)
6. [ANA, HidroWebService](#6-ana-hidrowebservice)
7. [Outras fontes](#7-outras-fontes)
8. [Parâmetros extraídos do painel municipal](#8-parâmetros-extraídos-do-painel-municipal)
9. [Plano de coleta](#9-plano-de-coleta)
10. [Limitações e riscos dos dados](#10-limitações-e-riscos-dos-dados)
11. [Ações pendentes](#11-ações-pendentes)

---

## 1. Resumo executivo

| Fonte | Uso no projeto | Acesso | Situação verificada |
|---|---|---|---|
| Defesa Civil SC, GraphQL Qualle | Tempo real de todas as estações do estado | Anônimo, sem chave | Funciona. 174 estações retornadas |
| Defesa Civil SC, GraphQL, consulta histórica | Série histórica | Bloqueada para anônimo | Não funciona. Retorna "Operação bloqueada" |
| Defesa Civil SC, REST anterior | Série de 5 em 5 minutos e barragens | Anônimo, sem chave | Funciona, com retenção de cerca de 80 dias |
| Open-Meteo Archive (ERA5) | Chuva histórica longa, desde 1940 | Anônimo, sem chave | Funciona. Testado em 1983, 2020 e 2023 |
| Open-Meteo Forecast | Previsão de chuva por ponto | Anônimo, sem chave | Funciona. 216 horas retornadas |
| Open-Meteo Flood (GloFAS) | Vazão prevista, variável auxiliar | Anônimo, sem chave | Funciona. Testado |
| ANA HidroWebService | Série histórica longa de nível de rio | Exige cadastro | Retorna 401 sem token. Cadastro pendente |
| CEMADEN | Chuva complementar | Portal e download | Não testado nesta rodada |
| INMET | Estação meteorológica automática | API pública | Não testado nesta rodada |
| Painel municipal PDC | Referência de parâmetros e limiares | Público | Consultado. Limiares extraídos |

O achado mais importante do levantamento: **a documentação de API que o professor forneceu está desatualizada**. A operação GraphQL `ListaEstacoes` descrita no material não existe mais na plataforma atual da Defesa Civil de SC, que foi migrada para outro fornecedor. A API REST anterior, por outro lado, continua no ar e é hoje a única via anônima para série histórica, ainda que com janela curta.

---

## 2. Estações relevantes para Presidente Getúlio

Distâncias calculadas a partir da sede do município (-27,0455 / -49,6243), com as coordenadas retornadas pela própria API.

| Código | Nome na API | Curso d'água | Distância | Papel no projeto |
|---|---|---|---|---|
| DCSC-00043 | PCD Presidente Getúlio | Rio dos Índios | 0 km | Estação alvo principal |
| DCSC-00174 | PCD ZAS Creche (Creche Agostinho Senem) | Ribeirão Revólver | 1,4 km | Estação alvo secundária |
| DCSC-00021 | PCD José Boiteux | Rio Itajaí do Norte | 10,1 km | Ponto de influência, montante |
| DCSC-00020 | PCD Ibirama | Rio Itajaí do Norte | 10,4 km | Referência de jusante |
| DCSC-00037 | PCD Dona Emma | Chuva | 12,4 km | Ponto de influência, montante |
| DCSC-00042 | DCSC Barragem Norte José Boiteux | Rio Hercílio / Itajaí do Norte | 18 km | Controle de vazão a montante |
| DCSC-00015 | PCD Witmarsum | Chuva | 26 km | Ponto de influência, cabeceira |
| DCSC-00036 | PCD Vitor Meireles | Chuva | 24 km | Ponto de influência, cabeceira |

Leituras de exemplo obtidas em 19/09/2026, às 13h18 UTC: DCSC-00043 com nível 1,79 m e chuva de 24h em 2,40 mm; DCSC-00021 com 2,65 m e 1,40 mm; DCSC-00020 com 2,33 m e 3,80 mm.

A Barragem Norte, a 18 km a montante, é a variável de controle que justifica o tratamento da vazão como exógena: a cota de fundo é 256 m, a cota do vertedouro é 302,7 m e, em 19/09/2026, o reservatório estava em 285,35 m, com 41,58 por cento de ocupação, com a galeria e a tulipa de 264 abertas e a tulipa de 258 fechada.

---

## 3. Defesa Civil de SC, plataforma atual (GraphQL)

**Endpoint:** `https://monitoramento.defesacivil.sc.gov.br/graphql` (POST, JSON). Existe também canal WebSocket em `wss://monitoramento.defesacivil.sc.gov.br/graphql` para assinatura.

**Autenticação:** nenhuma. O cliente do portal público envia o cabeçalho `Authorization` com valor indefinido.

**Restrição relevante:** o servidor só aceita operações que constam em uma lista prévia. Qualquer consulta fora dessa lista retorna HTTP 400 com a mensagem `Operação bloqueada.`, mesmo sendo válida do ponto de vista do schema. Na prática, isso significa que o consumo precisa reproduzir exatamente a operação registrada.

### 3.1 Operação Tags_data, funciona

Retorna o estado atual de todas as estações. Testada em 19/09/2026, com HTTP 200 e 174 estações.

Estrutura do retorno, por estação:

| Campo | Conteúdo |
|---|---|
| `codigo` | Código da estação, no padrão DCSC-00000 |
| `name` | Objeto com `prefix`, `general` e `local` |
| `timestamp` | Horário da leitura |
| `position` | `bacia`, `latitude`, `longitude`, `regiao`, `altitude` |
| `data.rio` | `rio_nome`, `rio_nivel`, `rio_nivel_tendencia`, `rio_area_drenagem` |
| `data.chuva.acumulado` | `s015`, `min005`, `min010`, `min015`, `h001`, `h003`, `h006`, `h012`, `h024`, `h048`, `h072`, `h096`, `h120`, `h144`, `h168` |
| `data.pressaoatmos` | Atual, tendência e histórico de 1h e 168h |
| `data.temperatura`, `data.senstermica`, `data.umidade`, `data.vento` | Atual, tendência e histórico |
| `data.barragem` | `comporta_1` a `comporta_10`, cada uma com `estado`, `habilitada` e `nome` |
| `filter.relacao` | Flags de capacidade: `tem_chuva_acumulada`, `tem_nivel_do_rio`, `tem_pressao_atmosferica`, `tem_sensacao_termica`, `tem_umidade`, `tem_vazao_do_rio`, `tem_vento`, `tem_barragem` |

Cada valor vem embrulhado em um objeto com `value`, `show`, `format` e `unit`, e boa parte traz `homologacao.relacao.valido`, que indica se a leitura foi homologada.

O parâmetro fixo da consulta é `clients: ["secretaria-de-defesa-civil"]` e o sistema interno é identificado como `Qualle_Meteorologia`.

### 3.2 Operação Historic, bloqueada

A operação existe no cliente do portal, com esta assinatura:

```graphql
query Historic($stationCode: String!, $startDate: String!, $endDate: String!, $interval: QueryInterval) {
  historic(
    system: Qualle_Hidrometeorologia
    client: "secretaria-de-defesa-civil"
    stationCode: $stationCode
    startDate: $startDate
    endDate: $endDate
    interval: $interval
    opts: {ordenacao: ASC}
  )
}
```

Todas as tentativas de execução anônima retornaram HTTP 400 com `Operação bloqueada.`, testando variações de formatação e de valor do parâmetro `interval`. A conclusão é que o acesso ao histórico por essa via depende de liberação da Defesa Civil de SC, e não de ajuste técnico do lado do cliente.

### 3.3 Operação Radares

`query Radares { radares: radares_getRadares { ARA { codigo timestamp } CHP { codigo timestamp } JVE { codigo timestamp } LON { codigo timestamp } } }`. Retorna os identificadores das imagens dos radares de Araranguá, Chapecó, Joinville e Lontras. Não testada nesta rodada, fica como fonte auxiliar para trabalho futuro.

---

## 4. Defesa Civil de SC, API REST anterior

**Base:** `https://api-dcsc.mks-unifique.ddns.net`. Sem autenticação. Documentada pelo próprio pessoal da Defesa Civil de SC no material da disciplina, com contato de referência Frederico Rudorff, `comal@defesacivil.sc.gov.br`.

Esta API continua no ar e é, hoje, a única via anônima para série temporal.

### 4.1 Inventário de estações

`GET /api/estacoes`

Retorna 182 estações, com nome, latitude, longitude, projeção e, quando existe sensor de nível, o nome do curso d'água. Foi por esse campo que se confirmou que DCSC-00043 mede o rio dos Índios e DCSC-00174 mede o ribeirão Revólver.

### 4.2 Série temporal

`GET /api/estacoes/dados?codigo={codigo}&data_inicial={iso8601}&data_final={iso8601}`

Exemplo real testado:

```
/api/estacoes/dados?codigo=DCSC-00043&data_inicial=2026-09-18T00:00-0300&data_final=2026-09-19T00:00-0300
```

Retorno, com 288 registros para o dia completo, ou seja, uma leitura a cada 5 minutos:

```json
{
  "codigo": "DCSC-00043",
  "dataInicial": "2026-09-18T00:00:00.000-03:00",
  "dataFinal": "2026-09-19T00:00:00.000-03:00",
  "dados": [
    { "timestamp": "2026-09-18T03:00:00.000Z", "chuva_acumulada_mm": 0, "rio_nivel_m": 1.8, "rio_nivel_alt": null },
    { "timestamp": "2026-09-18T03:05:00.000Z", "chuva_acumulada_mm": 0, "rio_nivel_m": 1.8, "rio_nivel_alt": null }
  ],
  "nome": "PCD Presidente Getúlio",
  "rio": "Rio dos Índios",
  "latitude": -27.045497,
  "longitude": -49.624281
}
```

Estações sem sensor de nível retornam `rio_nivel_m` nulo e apenas a chuva.

**Retenção medida.** Este é o ponto crítico do levantamento. Foi feita uma varredura dia a dia para descobrir até onde a série existe:

| Data consultada | Registros em DCSC-00043 |
|---|---|
| 2026-09-18 | 288 |
| 2026-09-01 | 288 |
| 2026-08-15 | 288 |
| 2026-07-10 | 288 |
| 2026-07-03 | 288 |
| 2026-07-01 | 0 |
| 2026-06-15 | 0 |
| 2026-03-15 | 0 |
| 2025-10-15 | 0 |
| 2024-11-15 | 0 |
| 2023-11-17 | 0 |

A janela começa entre 01/07/2026 e 03/07/2026, ou seja, **aproximadamente 78 a 80 dias corridos de retenção, em janela deslizante**. O mesmo comportamento foi observado em DCSC-00021, DCSC-00020 e DCSC-00037. Dado mais antigo que isso não está disponível por essa via.

Consequência direta para o projeto: os eventos de dezembro de 2020 e de 2023, que são os casos de referência do município, não podem ser recuperados por aqui. E cada dia que passa sem coleta é um dia perdido de forma definitiva.

**Estação do Revólver.** DCSC-00174 aparece no inventário, mas as consultas de série retornaram vazio em todas as datas testadas. O painel municipal mostra o nível desse ponto, o que indica que o município recebe esse dado por outra via. Item a tratar com a Defesa Civil municipal.

### 4.3 Barragens

`GET /api/barragens`

Retorna `barragemNorte`, `barragemOeste` e `barragemSul`. Para a Barragem Norte, que é a que interessa ao projeto, o retorno traz `limites` (mínimo 256, vertedouro 302,7), o estado de cada comporta (`galeria`, `tulipa258`, `tulipa264`) e um histórico da última semana com nível em metros e percentual de ocupação.

Diferente das PCDs, a série da Barragem Norte tem registros esparsos, mas **profundos no tempo**: as consultas retornaram dados para 17/12/2020 (8,15 m), 17/11/2023 (entre 29,50 m e 31,05 m, com 8 leituras no dia) e para vários pontos de 2024, 2025 e 2026. A quantidade de leituras por dia é baixa, entre 1 e 8, mas serve como referência histórica da operação do reservatório nos eventos de interesse.

**Observação de uso.** A própria Defesa Civil de SC pede, no material de especificação, que o consumo não seja feito direto do navegador do usuário final, e sim que a plataforma consuma e replique os dados. Isso reforça a arquitetura com coleta no servidor descrita no documento de arquitetura.

---

## 5. Open-Meteo

Três APIs distintas, todas sem chave, todas testadas.

### 5.1 Archive API (reanálise ERA5)

`https://archive-api.open-meteo.com/v1/archive`

Resolve o problema de chuva histórica longa. Testes realizados para as coordenadas do município:

| Período testado | Horas retornadas | Chuva total | Maior acumulado em 6h |
|---|---|---|---|
| 05 a 10/07/1983 | 144 | 263,1 mm | 45,6 mm |
| 15 a 18/12/2020 | 96 | 67,0 mm | 34,4 mm |
| 15 a 18/11/2023 | 96 | 53,4 mm | 19,3 mm |

**Ressalva importante.** Para o evento de dezembro de 2020, a reanálise indica 34,4 mm como maior acumulado de 6 horas, enquanto o relato do evento aponta cerca de 120 mm em 6 horas na cidade. A diferença é esperada: a ERA5 trabalha em grade de dezenas de quilômetros e suaviza picos convectivos, que é justamente o tipo de chuva que provoca enxurrada. A conclusão prática é que a ERA5 serve para caracterizar contexto e regime de chuva ao longo de anos, e não como verdade de campo para eventos extremos. Onde houver pluviômetro, o pluviômetro ganha.

### 5.2 Forecast API

`https://api.open-meteo.com/v1/forecast`

Teste em 19/09/2026 retornou 216 horas de série, de 17/09 a 25/09, combinando dias passados e previsão, com `precipitation` e `precipitation_probability` por hora. Permite escolher e comparar modelos, o que sustenta o uso de média de modelos.

### 5.3 Flood API (GloFAS)

`https://flood-api.open-meteo.com/v1/flood`

Retorna `river_discharge` diária. No teste, devolveu 12 dias de série, com valores na faixa de 141 a 262 m³/s para a célula da grade. Como a grade é grosseira e pode não representar o rio dos Índios, entra como variável auxiliar e não como referência.

---

## 6. ANA, HidroWebService

`https://www.ana.gov.br/hidrowebservice/` e os endpoints REST em `https://www.snirh.gov.br/hidroweb/rest/api/...`

Todos os endpoints testados em 19/09/2026 retornaram **HTTP 401**, com a mensagem `Token de Autenticação da API Inexistente ou mal Formatado, Verifique!`. Foram testados os caminhos de inventário de estações, documento de séries convencionais e série histórica.

Procedimento de acesso, conforme documentação da ANA:

1. Enviar e-mail para `hidro@ana.gov.br`, com assunto no formato `[CPF/CNPJ] - Solicitação de acesso à API HidroWebService para consumo de dados`, informando nome, instituição, CPF e e-mail.
2. Receber identificador e senha.
3. Autenticar em `GET /EstacoesTelemetricas/OAUth/v1`, com os cabeçalhos `Identificador` e `Senha`, obtendo um token válido por 60 minutos.
4. Consumir os endpoints de inventário e de série, com o token como Bearer.

Estação de referência já identificada para a bacia: **83360000, José Boiteux, rio Itajaí do Norte**. A verificação do período coberto por essa estação depende do cadastro, e por isso está listada como pendência PE09 na especificação.

---

## 7. Outras fontes

| Fonte | Endereço | Uso previsto | Situação |
|---|---|---|---|
| CEMADEN | `https://mapainterativo.cemaden.gov.br/` | Pluviômetros automáticos, complemento de chuva | Não testado nesta rodada. Download histórico por formulário |
| INMET | `https://apitempo.inmet.gov.br/estacoes/T` e `https://portal.inmet.gov.br/dadoshistoricos` | Estação meteorológica automática e histórico | Não testado nesta rodada |
| EPAGRI/CIRAM | `https://ciram.epagri.sc.gov.br/` | Boletins hidrológicos e dados horários de estações de SC | Não testado nesta rodada. Exige cadastro |
| Radar da Defesa Civil de SC | Operação `Radares` do GraphQL | Nowcast de chuva | Fonte auxiliar, trabalho futuro |

Essas fontes entram como complemento. Nenhuma delas é caminho crítico para a primeira versão do sistema, porque a cobertura de chuva nos pontos de influência já é atendida pela rede da Defesa Civil de SC.

---

## 8. Parâmetros extraídos do painel municipal

O portal `pdc.presidentegetulio.sc.gov.br` foi inspecionado para levantar os parâmetros oficiais em uso pelo município. Os valores abaixo passam a ser a referência do projeto, sujeitos a confirmação formal (pendência PE05).

**Limiares de risco:**

| Curso d'água | Observação | Atenção | Alerta |
|---|---|---|---|
| Rio dos Índios | 4,00 m | 4,50 m | 5,50 m |
| Ribeirão Revólver | 2,50 m | 3,00 m | 3,50 m |

**Pontos de monitoramento usados pelo município:**

| Nome no painel | Estação correspondente | Situação na API pública |
|---|---|---|
| Centro | SDC-SC Presidente Getúlio (DCSC-00043) | Disponível |
| Revólver | Creche Agostinho Senem (DCSC-00174) | No inventário, sem série |
| Dona Emma | SDC-SC Dona Emma (DCSC-00037) | Disponível |
| Witmarsum | SDC-SC Witmarsum (DCSC-00015) | Disponível |
| Serra dos Índios | Posto de Saúde | Não está na API pública |
| Serra Vencida | Escola Serra Vencida | Não está na API pública |
| Serra Mirador | Mirante das Antenas | Não está na API pública |

A verificação foi feita por proximidade de coordenadas contra o inventário completo de 182 estações. As três estações de serra não têm correspondente dentro de um raio razoável, o que indica rede própria do município. Conseguir acesso a esses três pontos é relevante, porque eles cobrem a cabeceira das bacias urbanas, que é exatamente onde nasce a enxurrada. Isso está registrado como pendência PE06.

---

## 9. Plano de coleta

Configuração proposta para o serviço de ingestão, considerando os limites e o comportamento observado de cada fonte.

| Fonte | Endpoint | Frequência | Observação |
|---|---|---|---|
| DCSC GraphQL | `Tags_data` | A cada 5 minutos | Uma chamada traz todas as estações, o que evita múltiplas requisições |
| DCSC REST | `/api/estacoes/dados` | A cada 30 minutos, por estação configurada | Usado para preencher lacunas e garantir a granularidade de 5 minutos |
| DCSC REST | `/api/barragens` | A cada 30 minutos | Volume pequeno |
| DCSC REST | `/api/estacoes` | Diária | Inventário muda pouco |
| Open-Meteo Forecast | `/v1/forecast` | A cada 1 hora, por ponto de influência | Previsão não muda em intervalo menor |
| Open-Meteo Archive | `/v1/archive` | Carga inicial, depois mensal | Preenche o histórico longo de chuva |
| ANA | HidroWebService | Diária, após liberação do cadastro | Depende de PE09 |

**Carga inicial obrigatória:** no primeiro dia de operação, baixar os cerca de 80 dias disponíveis na API REST para todas as estações configuradas. Isso garante a única janela de histórico de 5 minutos que ainda existe.

**Volume estimado:** 288 leituras por dia por estação, com 8 estações configuradas, resulta em aproximadamente 2.300 registros por dia, 70 mil por mês e 840 mil por ano. É volume pequeno para um banco relacional, e não exige infraestrutura especial.

---

## 10. Limitações e riscos dos dados

| ID | Limitação | Efeito no projeto | Como tratar |
|---|---|---|---|
| LD01 | Retenção de cerca de 80 dias na única API anônima com série | Impede treinar com os eventos históricos do município | Coleta contínua desde já, pedido institucional de histórico, uso da ERA5 para chuva |
| LD02 | Consulta histórica do GraphQL bloqueada para anônimo | Fecha a via mais completa de histórico | Pedido formal à Defesa Civil de SC (PE10) |
| LD03 | ANA exige cadastro com prazo indefinido | Atrasa o acesso à série longa de nível | Solicitar imediatamente (PE09) e seguir sem ela enquanto isso |
| LD04 | ERA5 suaviza picos de chuva convectiva | Subestima justamente os eventos de enxurrada | Usar só para contexto e regime, nunca como verdade de campo |
| LD05 | Estação do Revólver sem série pública | Deixa a segunda estação alvo sem histórico próprio | Tratar com o município (PE06) e, enquanto isso, operar só com o tempo real |
| LD06 | Três estações municipais fora da API pública | Perde cobertura de cabeceira | Solicitar acesso ao município (PE06) |
| LD07 | Nenhuma das APIs tem contrato estável nem versionamento | Quebra silenciosa de integração | Adaptador isolado por fonte, validação de contrato e painel de qualidade (RNF11, RF36) |
| LD08 | A documentação fornecida pelo professor já estava desatualizada | Mostra a velocidade com que essas fontes mudam | Registrar o contrato observado neste documento e revalidar periodicamente |

---

## 11. Ações pendentes

| ID | Ação | Responsável | Prazo desejado |
|---|---|---|---|
| PE09 | Solicitar cadastro na API HidroWebService da ANA | Equipe | Imediato, por causa do prazo de resposta |
| PE10 | Solicitar à Defesa Civil de SC o acesso ao histórico completo e à operação `Historic` | Equipe, com apoio do professor | Imediato |
| PE05 | Confirmar limiares oficiais com a Defesa Civil municipal | Equipe | Antes da publicação do portal |
| PE06 | Solicitar ao município o acesso aos dados das três estações de serra e da estação do Revólver | Equipe | Antes do treino do modelo |
| PE07 | Levantar com a Defesa Civil a lista de eventos de alagamento com data e hora | Equipe | Antes da avaliação do modelo |
| AC01 | Subir o serviço de ingestão em ambiente estável e iniciar a coleta contínua | Equipe | Imediato, cada dia sem coleta é dado perdido |
| AC02 | Executar a carga inicial dos 80 dias disponíveis | Equipe | No mesmo dia em que a ingestão subir |
| AC03 | Testar CEMADEN, INMET e EPAGRI e registrar o resultado neste documento | Equipe | Durante a Fase 3 |
