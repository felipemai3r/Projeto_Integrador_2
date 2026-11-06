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
| Painel municipal PDC, portal | Referência de parâmetros e limiares | Público | Consultado. Limiares extraídos |
| Painel municipal PDC, API | Série de 5 em 5 minutos de 7 estações, incluindo o Revólver e as 3 de serra, desde 13/09/2025 | Chave fornecida pela Defesa Civil municipal | Funciona. Validada em 05/11/2026 (seção 8.1) |

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

**Estação do Revólver.** DCSC-00174 aparece no inventário, mas as consultas de série nesta API retornaram vazio em todas as datas testadas. O painel municipal mostra o nível desse ponto, o que indicava que o município recebe esse dado por outra via. Resolvido: a API do painel municipal (seção 8.1) entrega a série completa dessa estação, desde 13/09/2025.

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

**Limiares de risco** (os limites do painel foram mapeados para a escala da Defesa Civil de SC: o antigo "observação" é Atenção, o antigo "atenção" é Alerta e o antigo "alerta" é Alerta alto; a faixa Extremo ainda não tem cota):

| Curso d'água | Atenção | Alerta | Alerta alto |
|---|---|---|---|
| Rio dos Índios | 4,00 m | 4,50 m | 5,50 m |
| Ribeirão Revólver | 2,50 m | 3,00 m | 3,50 m |

**Pontos de monitoramento usados pelo município:**

| Nome no painel | Estação correspondente | Situação na API pública |
|---|---|---|
| Centro | SDC-SC Presidente Getúlio (DCSC-00043) | Disponível |
| Revólver | Creche Agostinho Senem (DC-PEU-001 na API do painel; no banco, DCSC-00174) | No inventário estadual, sem série; série completa na API do painel |
| Dona Emma | SDC-SC Dona Emma (DCSC-00037) | Disponível; também na API do painel |
| Witmarsum | SDC-SC Witmarsum (DCSC-00015) | Disponível; também na API do painel |
| Serra dos Índios | Posto de Saúde (DC-PEU-003) | Não está na API pública estadual; série na API do painel |
| Serra Vencida | Escola Serra Vencida (DC-PEU-004) | Não está na API pública estadual; série na API do painel |
| Serra Mirador | Mirante das Antenas (DC-PEU-002) | Não está na API pública estadual; série na API do painel |

A verificação foi feita por proximidade de coordenadas contra o inventário completo de 182 estações. As três estações de serra não têm correspondente dentro de um raio razoável, o que indica rede própria do município. Elas cobrem a cabeceira das bacias urbanas, que é exatamente onde nasce a enxurrada. O acesso a elas e ao Revólver, que era a pendência PE06, foi resolvido com a API do painel descrita a seguir.

### 8.1 API do painel municipal (PDC)

**Validada em 05/11/2026**, com chamadas reais. Pendência PE06 **resolvida**: a Defesa Civil municipal forneceu a chave de acesso.

**Base:** `https://uizatcahxcyscjbkxnzp.supabase.co/functions/v1/stations-api`. Somente leitura. Limite de 120 chamadas por minuto.

**Autenticação.** Cabeçalho `x-api-key` com a chave fornecida pela Defesa Civil municipal. A chave é um segredo: fica só em `desenvolvimento/.env` (variável `PDC_API_KEY`), nunca em código, teste, fixture, log ou documento. No compose, é repassada ao serviço `ingestor`. Sem chave, o coletor desta fonte não é agendado e o restante do sistema funciona como antes.

**Endpoints:**

| Endpoint | Retorno |
|---|---|
| `GET /stations` | `{"data": [{"sta_name", "sta_code"}], "count": 7}` |
| `GET /latest` | `{"data": [uma leitura por estação]}` |
| `GET /readings?code=&from=&to=&limit=&cursor=&fields=` | `{"data": [...], "next_cursor": string ou null}`. `from` e `to` em ISO 8601; `limit` de 1 a 1000; `fields` lista as colunas desejadas. Janela máxima de 31 dias por consulta (excedê-la devolve HTTP 400); sem `from` e `to`, vale as últimas 24 horas |

**Comportamentos observados e tratados no adaptador:**

- O **cursor é inclusivo**: a última linha de uma página reaparece no início da seguinte. Com `limit=1` o cursor nunca avança. O adaptador deduplica por `id`, recusa `limit` menor que 2 e para quando o cursor não avança.
- Código de estação desconhecido devolve HTTP 200 com lista vazia, não erro.
- As leituras vêm em ordem cronológica crescente.
- Excesso de chamadas devolve HTTP 429; o adaptador espera e tenta de novo até 3 vezes, e espaça as chamadas em 0,6 s (no máximo 100 por minuto).

**Estações:**

| `sta_code` na API | Nome na API | Código no nosso banco | Observação |
|---|---|---|---|
| DC-PEU-001 | Creche Agostinho Senem | DCSC-00174 | Mesma estação física do "PCD ZAS Creche" (Ribeirão Revólver), coordenadas idênticas. Não há estação nova; as leituras vão para a DCSC-00174 |
| DC-PEU-002 | Mirante das Antenas | DC-PEU-002 | "Serra Mirador". Só chuva. Papel de influência |
| DC-PEU-003 | Posto de Saúde | DC-PEU-003 | "Serra dos Índios". Só chuva. Papel de influência |
| DC-PEU-004 | Escola Serra Vencida | DC-PEU-004 | "Serra Vencida". Só chuva. Papel de influência |
| DCSC-00037 | SDC-SC Dona Emma | DCSC-00037 | Já cadastrada |
| DCSC-00043 | SDC-SC Presidente Getúlio | DCSC-00043 | Já cadastrada |
| DCSC-00015 | SDC-SC Witmarsum | DCSC-00015 | Já cadastrada |

**Campos de cada leitura:** `id`, `created_at`, `sta_timestamp`, `sta_code`, `sta_name`, `river_level` (m), `rainfall_1h` a `rainfall_168h` (mm), `temperature`, `humidity`, `wind_speed`, `wind_guts`, `wind_direction`, `atm_pressure`, `solar_radiation`, `feels_like`. Na prática só `river_level` e `rainfall_1h` são aproveitados; os acumulados de 3 h em diante vêm nulos, e os campos meteorológicos aparecem em alguns pontos (por exemplo, no Mirante das Antenas), mas não entram no modelo. Eles ficam apenas no payload bruto.

**Semântica e armadilhas:**

1. **Fuso.** `created_at` é UTC correto, por exemplo `2026-11-04T19:12:27.00648+00:00`. `sta_timestamp` vem em **hora local (-03:00), mas rotulado `+00:00`**, portanto 3 horas deslocado. O sistema usa `created_at` como `medido_em`. Conferido contra a API REST estadual: o nível de `created_at` bate minuto a minuto.
2. **`rainfall_1h` é janela móvel**, a chuva acumulada na última hora, a mesma semântica do `h001` do GraphQL. Por isso é gravada como `chuva_h001_mm`, e **não** como `chuva_acumulada_mm`, que é o incremento de 5 minutos da API REST; gravar uma janela móvel ali faria o modelo, que soma incrementos, contar a chuva em dobro. Conferência: `rainfall_1h` às 16:47 UTC de 04/11/2026 era 7,6 mm e a soma dos incrementos da API REST nos 60 minutos anteriores era 7,8 mm.
3. **Pico espúrio real na fonte.** Em 04/11/2026 às 19:12 UTC, DCSC-00043 registrou `rainfall_1h` de 248,28 mm, isolado entre leituras de 0,2 mm. A validação de plausibilidade (`quality.avaliar`) marca `chuva_h001_mm` acima de 150 mm como suspeita, e a leitura suspeita não entra nas consultas que exigem qualidade `ok`.
4. **Duas fontes para as mesmas estações.** Para DCSC-00043, DCSC-00037, DCSC-00015 e DCSC-00174, a API do painel e o GraphQL estadual publicam a mesma medição física. Cada leitura guarda a sua `fonte`, então as duas séries coexistem sem conflito; as consultas que precisam de uma só fonte filtram por ela.
5. **Retenção.** Histórico completo desde **13/09/2025** para todas as estações, a cada 5 minutos, sem janela deslizante conhecida. Isso é mais de um ano de dados, contra os cerca de 80 dias da API REST estadual (LD01).

**Plano de coleta.** Coleta contínua a cada 5 minutos, janela das últimas 1 hora por estação, defasada alguns segundos dos outros jobs; reexecutar não duplica (`UNIQUE` e `ON CONFLICT DO NOTHING`). Carga histórica única, depois da subida do serviço: `python -m ingestor.carga_pdc` (janelas de 7 dias, ver `desenvolvimento/README.md`). Uma estação fora do ar não interrompe as demais. O canário diário de contrato inclui esta fonte.

---

## 9. Plano de coleta

Configuração proposta para o serviço de ingestão, considerando os limites e o comportamento observado de cada fonte.

| Fonte | Endpoint | Frequência | Observação |
|---|---|---|---|
| DCSC GraphQL | `Tags_data` | A cada 5 minutos | Uma chamada traz todas as estações, o que evita múltiplas requisições |
| DCSC REST | `/api/estacoes/dados` | A cada 30 minutos, por estação configurada | Usado para preencher lacunas e garantir a granularidade de 5 minutos |
| DCSC REST | `/api/barragens` | A cada 30 minutos | Volume pequeno |
| API do painel municipal (PDC) | `/readings` | A cada 5 minutos, janela de 1 hora, por estação | Requer chave (`PDC_API_KEY`). Carga histórica desde 13/09/2025 com `ingestor.carga_pdc` |
| DCSC REST | `/api/estacoes` | Diária | Inventário muda pouco |
| Open-Meteo Forecast | `/v1/forecast` | A cada 1 hora, por ponto de influência | Previsão não muda em intervalo menor |
| Open-Meteo Archive | `/v1/archive` | Carga inicial, depois mensal | Preenche o histórico longo de chuva |
| ANA | HidroWebService | Diária, após liberação do cadastro | Depende de PE09 |

**Carga inicial obrigatória:** no primeiro dia de operação, baixar os cerca de 80 dias disponíveis na API REST para todas as estações configuradas. Isso garante a única janela de histórico de 5 minutos que ainda existe.

**Volume estimado:** 288 leituras por dia por estação, com 8 estações configuradas, resulta em aproximadamente 2.300 registros por dia, 70 mil por mês e 840 mil por ano. As 3 estações de serra da API do painel e a duplicação das séries por fonte elevam o total, sem mudar a conclusão. É volume pequeno para um banco relacional, e não exige infraestrutura especial.

---

## 10. Limitações e riscos dos dados

| ID | Limitação | Efeito no projeto | Como tratar |
|---|---|---|---|
| LD01 | Retenção de cerca de 80 dias na única API anônima com série | Impede treinar com os eventos históricos do município | Coleta contínua desde já, pedido institucional de histórico, uso da ERA5 para chuva |
| LD02 | Consulta histórica do GraphQL bloqueada para anônimo | Fecha a via mais completa de histórico | Pedido formal à Defesa Civil de SC (PE10) |
| LD03 | ANA exige cadastro com prazo indefinido | Atrasa o acesso à série longa de nível | Solicitar imediatamente (PE09) e seguir sem ela enquanto isso |
| LD04 | ERA5 suaviza picos de chuva convectiva | Subestima justamente os eventos de enxurrada | Usar só para contexto e regime, nunca como verdade de campo |
| LD05 | Estação do Revólver sem série pública estadual | Deixava a segunda estação alvo sem histórico próprio | **Resolvida** pela API do painel municipal (PE06): série desde 13/09/2025 |
| LD06 | Três estações municipais fora da API pública estadual | Perdia cobertura de cabeceira | **Resolvida** pela API do painel municipal (PE06) |
| LD07 | Nenhuma das APIs tem contrato estável nem versionamento | Quebra silenciosa de integração | Adaptador isolado por fonte, validação de contrato e painel de qualidade (RNF11, RF36) |
| LD08 | A documentação fornecida pelo professor já estava desatualizada | Mostra a velocidade com que essas fontes mudam | Registrar o contrato observado neste documento e revalidar periodicamente |
| LD09 | A API do painel municipal depende de uma chave dada pelo município, sem contrato estável, e o `sta_timestamp` tem fuso errado | Quebra de integração ou erro de 3 h no horário | Usar só `created_at`; canário de contrato diário; chave só no `.env` (seção 8.1) |

---

## 11. Ações pendentes

| ID | Ação | Responsável | Prazo desejado |
|---|---|---|---|
| PE09 | Solicitar cadastro na API HidroWebService da ANA | Equipe | Imediato, por causa do prazo de resposta |
| PE10 | Solicitar à Defesa Civil de SC o acesso ao histórico completo e à operação `Historic` | Equipe, com apoio do professor | Imediato |
| PE05 | Confirmar limiares oficiais com a Defesa Civil municipal | Equipe | Antes da publicação do portal |
| PE06 | ~~Solicitar ao município o acesso aos dados das três estações de serra e da estação do Revólver~~ **Resolvida em 05/11/2026**: chave da API do painel recebida (seção 8.1) | Equipe | Concluída |
| AC04 | Executar a carga histórica da API do painel municipal (`python -m ingestor.carga_pdc`) | Equipe | No mesmo dia em que a chave for configurada |
| PE07 | Levantar com a Defesa Civil a lista de eventos de alagamento com data e hora | Equipe | Antes da avaliação do modelo |
| AC01 | Subir o serviço de ingestão em ambiente estável e iniciar a coleta contínua | Equipe | Imediato, cada dia sem coleta é dado perdido |
| AC02 | Executar a carga inicial dos 80 dias disponíveis | Equipe | No mesmo dia em que a ingestão subir |
| AC03 | Testar CEMADEN, INMET e EPAGRI e registrar o resultado neste documento | Equipe | Durante a Fase 3 |
