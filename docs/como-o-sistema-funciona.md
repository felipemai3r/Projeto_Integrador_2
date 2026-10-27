# Como o sistema funciona

Este documento mostra o sistema de apoio à decisão para enchentes de Presidente Getúlio (SC) como ele está em 22/10/2026. Ele cobre de onde vêm os dados e como são tratados, como o risco é classificado e como os avisos chegam às pessoas. Também explica em detalhe como a previsão e a simulação de chuva são calculadas, e lista as limitações conhecidas.

O sistema é uma **ferramenta de apoio**. A fonte oficial de alertas é sempre a Defesa Civil de Presidente Getúlio (199). Todas as telas e todos os avisos repetem isso.

---

## 1. Visão geral

```
 Fontes públicas              Backend (Docker)                         Usuários
 ───────────────              ──────────────────────────────────       ─────────────────
 Defesa Civil SC  ──┐
  (GraphQL, REST,   │   ingestor ──► PostgreSQL ◄── api (FastAPI) ◄──► PWA (React)
   barragens)       ├──►  coleta,        ▲            │  avaliador de     painel, previsão,
 Open-Meteo         │     validação,     │            │  risco (1/min)    mapa, avisos,
  (previsão, ERA5) ─┘     gravação       │            ├─► push (VAPID)    moderação
                                         │            └─► e-mail (SMTP / Mailpit)
                              treinador ─┘  retreino diário dos modelos (07:00 UTC)
```

| Serviço | O que faz |
|---|---|
| `db` | PostgreSQL 16. Guarda leituras, alertas, modelos, registros da população, inscrições |
| `migrate` | Aplica as migrações (Alembic) e o *seed* (estações, fontes, limiares) ao subir |
| `ingestor` | Coleta as fontes em intervalos fixos, valida e grava |
| `api` | API pública em `/api`. Também roda o **avaliador de risco** a cada minuto |
| `treinador` | Retreina e valida os modelos de previsão uma vez por dia |
| `mailpit` | Caixa de e-mail local (só em desenvolvimento), em `http://localhost:8025` |
| frontend | PWA em React com o design Farol. Em produção é servido pelo Nginx |

---

## 2. Dados: de onde vêm e como são tratados

### 2.1 Fontes e frequência de coleta

| Fonte | Conteúdo | Frequência |
|---|---|---|
| Defesa Civil SC, GraphQL | Leitura mais recente das estações (nível, chuva) | a cada 5 min |
| Defesa Civil SC, API REST | Histórico em 5 min, usado para fechar lacunas | a cada 30 min |
| Defesa Civil SC, barragens | Cota do reservatório e comportas da Barragem Norte | a cada 30 min |
| Open-Meteo, previsão | Chuva prevista | a cada 1 h |
| Open-Meteo, ERA5 | Reanálise de chuva horária desde nov/2020 (carga manual) | sob demanda |

Há ainda um "canário de contrato" diário (09:00 UTC) que avisa no log se alguma fonte mudou de formato. Um alarme dispara quando uma fonte para de mandar dados.

### 2.2 Estações

| Estação | Código | Mede |
|---|---|---|
| Rio dos Índios (Presidente Getúlio) | DCSC-00043 | nível e chuva. **É o alvo principal** |
| Ribeirão Revólver | DCSC-00174 | listada pela Defesa Civil, mas **sem série pública** |
| Ibirama | DCSC-00020 | nível e chuva |
| José Boiteux | DCSC-00021 | nível e chuva |
| Dona Emma | DCSC-00037 | só chuva |
| Witmarsum | DCSC-00015 | só chuva |
| Vitor Meireles | DCSC-00036 | só chuva |
| Barragem Norte | DCSC-00042 | cota do reservatório (2 leituras por dia) |

### 2.3 Validação de cada leitura (plausibilidade física)

Toda leitura recebe uma qualidade antes de ser usada:

- nível negativo ou acima de 15 m: **descartada**;
- horário no futuro (com tolerância de 2 min): **descartada**;
- salto de nível maior que 100 cm em 5 minutos: **suspeita**;
- chuva de 1 h acima de 150 mm: **suspeita**.

Só as leituras com qualidade `ok` entram na previsão.

### 2.4 Agregação por hora

O modelo trabalha com **uma linha por hora**. As leituras de 5 minutos viram valores horários assim:

- **Nível:** é a média das leituras da hora. A hora precisa ter pelo menos **6** leituras das ~12 esperadas.
- **Chuva:** é a soma dos incrementos de 5 minutos. A hora precisa ter pelo menos **9 de 12** leituras (75%).

Uma hora sem cobertura suficiente fica **vazia (desconhecida), nunca zero**. "Não sabemos se choveu" é diferente de "não choveu". Esse princípio vale para todo o sistema.

### 2.5 Dado desatualizado

Uma estação cuja última leitura tem mais de **30 minutos** aparece como "desatualizada" (RN04). Dado desatualizado **nunca** dispara nem encerra um alerta.

---

## 3. Risco observado e alertas

### 3.1 Faixas

Cada estação com nível tem até quatro limites (hoje três, porque a cota do risco extremo ainda não foi cadastrada). A faixa é a mais grave cujo limite o nível atingiu:

| Faixa | Rio dos Índios | Ribeirão Revólver |
|---|---|---|
| Normal | abaixo de 4,00 m | abaixo de 2,50 m |
| Atenção (amarelo) | a partir de 4,00 m | a partir de 2,50 m |
| Alerta (laranja) | a partir de 4,50 m | a partir de 3,00 m |
| Alerta alto (vermelho) | a partir de 5,50 m | a partir de 3,50 m |
| Aja imediatamente, risco extremo (roxo) | sem cota cadastrada | sem cota cadastrada |

Os limites vêm do painel municipal e ainda **aguardam confirmação oficial** (PE05). Ibirama e José Boiteux **não têm limites**, porque nenhuma fonte os fornece, e por isso aparecem sem faixa.

### 3.2 Tendência

- **Taxa:** é a diferença entre o nível de agora e o de 1 h atrás, em cm/h.
- **Aceleração:** é a taxa de agora menos a taxa de 1 h atrás.
- **Classificação:** abaixo de 2 cm/h, para cima ou para baixo, o rio é "estável".
- **Na tela:** sempre aparece número e sentido ("Subindo 8 cm por hora e acelerando"), nunca só uma seta.

### 3.3 Avaliador de alertas (a cada minuto)

Roda dentro da API, com uma trava no banco para que só uma instância avalie por vez.

- **Subida (RN02):** a passagem para uma faixa **mais grave** abre um alerta e dispara os avisos.
- **Descida com histerese (RN10):** para voltar a uma faixa menos grave, as **3 últimas leituras** precisam estar abaixo da faixa vigente. Sem isso, um rio oscilando em torno do limite geraria um entra-e-sai de alertas.
- **Encerramento:** quando volta ao normal, avisa **só quem recebeu a abertura** daquele episódio.

---

## 4. Avisos para a população

### 4.1 Notificação no celular (Web Push)

- **Inscrição:** não precisa de cadastro. O navegador gera uma inscrição, e o servidor guarda só o endereço técnico de entrega e as chaves.
- **Escolhas da pessoa:** o rio (Índios ou todos) e a faixa mínima (Atenção, Alerta, Alerta alto ou risco extremo).
- **Requisitos:** só funciona no app publicado, que tem *service worker*. No iPhone, só depois de "Adicionar à Tela de Início".
- **Teste:** o botão "Enviar aviso de teste" manda uma notificação apenas para o próprio aparelho.
- **Inscrição morta:** se o serviço de push responder 404 ou 410, a pessoa desinstalou ou revogou, e a inscrição é desativada.
- **Proteção (SSRF):** o servidor só aceita endereços dos serviços de push conhecidos (Google, Mozilla, Microsoft, Apple).

### 4.2 E-mail

1. A pessoa informa o e-mail, o rio e a faixa.
2. O sistema manda um **link de confirmação**, válido por 48 h. Sem confirmar, nada é enviado. Isso impede cadastrar o e-mail de outra pessoa.
3. O link abre a tela Avisos, que confirma com um POST. Assim, um filtro de e-mail que "clica" nos links sozinho não confirma nada por engano.
4. Confirmado, a pessoa recebe os mesmos avisos do push, de abertura e de encerramento.
5. Todo e-mail traz um link para **cancelar**. Esse link é assinado com HMAC e continua válido em qualquer e-mail antigo. Cancelar **apaga** o e-mail e o histórico de envios (LGPD).
6. O banco guarda só o **hash** do token de confirmação.

Em desenvolvimento, os e-mails vão para o Mailpit (`http://localhost:8025`). Em produção, basta configurar o SMTP no `.env`.

### 4.3 Conteúdo de todo aviso

O aviso diz o nível, a tendência e se o dado é **observado ou previsto** (RN03). Também lembra que a fonte oficial é a Defesa Civil (RN09).

---

## 5. Registros da população (mapa "Onde alagou")

### 5.1 Registro

- **Quem registra:** qualquer pessoa, sem login.
- **O que informa:** o ponto no mapa (dentro do município), quando aconteceu (até 1 ano atrás), o tipo de impacto (rua intransitável, água na calçada, água dentro de imóvel, outro), uma descrição opcional e uma foto opcional.
- **Foto:** é reduzida, e os **metadados (EXIF) são removidos**, o que tira localização e modelo do aparelho.
- **Contexto:** o sistema anexa ao registro o nível dos rios e a chuva das 24 h no momento do ocorrido.
- **Abuso:** o limite é de 5 registros por hora por IP.

### 5.2 O que aparece no mapa

- **Imediatamente:** o registro entra como **pendente** e já aparece no mapa, com contorno tracejado e o selo "Aguardando conferência da Defesa Civil".
- **Enquanto pendente:** o público vê só o local, o tipo e a hora. **Descrição e foto ficam escondidas até a moderação**, porque ainda não foram conferidas.
- **Depois de validado:** o contorno fica cheio e a descrição e a foto aparecem.
- **Período:** o filtro tem 6 horas, 1 dia, 30 dias e 1 ano.

### 5.3 Curtir e denunciar

- **Curtir ("vi também")** e **denunciar** não exigem login. Cada aparelho conta uma vez por tipo, e as duas ações podem ser desfeitas.
- **Anonimato:** o aparelho é identificado por um código gerado no navegador, e o banco guarda só o **hash** desse código (RN06).
- **Motivos da denúncia:** não alagou ou informação falsa, local errado, conteúdo impróprio, outro.
- **Quem vê o quê:** o público vê só as curtidas. A moderação vê curtidas, denúncias e motivos.
- **Ocultação:** um registro **pendente com 3 denúncias sai do mapa público** até a moderação olhar. Registros já validados não somem por denúncia.

### 5.4 Moderação

- **Acesso:** quem modera (Defesa Civil ou equipe) entra em `/moderacao` com e-mail e senha.
- **Ações:** validar, rejeitar (com motivo obrigatório) ou reclassificar o tipo.
- **Histórico:** cada ação fica registrada, com quem fez, quando, o antes e o depois (RF26).
- **Calibração (RN05):** só registros validados podem ser usados para calibrar modelos.

---

## 6. Previsão do nível

### 6.1 Ideia central

O modelo **não prevê o nível diretamente**. Ele prevê **quanto o nível vai variar** daqui a *h* horas, em centímetros:

```
alvo(t, h) = nível(t + h) − nível(t)        (em cm)
nível previsto(t + h) = nível(t) + variação prevista
```

Prever a variação torna natural a comparação com a **persistência** ("o nível daqui a *h* horas será igual ao de agora", ou seja, variação zero). Esse é o concorrente que o modelo precisa vencer.

Os horizontes são **1, 3, 6, 12 e 24 horas**, e cada um tem um modelo próprio.

### 6.2 Variáveis de entrada (uma linha por hora *t*)

**Regra de ouro:** toda variável na hora *t* usa **só dado até *t***. Um teste automatizado prova isso: ele corta a série em *t* e confere que nada muda.

| Grupo | Variáveis |
|---|---|
| Nível do alvo | nível (m), taxa em 1 h (cm), taxa média em 3 h (cm/h), aceleração (cm) |
| Rios vizinhos | nível e taxa em 1 h de **José Boiteux** e **Ibirama** |
| Chuva acumulada | para cada um dos 5 pontos (cidade, Dona Emma, José Boiteux, Witmarsum, Vitor Meireles), em **1, 3, 6, 12, 24, 48, 72 e 168 h** |
| Interações | chuva de 6 h em Dona Emma × chuva de 6 h em José Boiteux (hipótese de chuva simultânea nas cabeceiras); nível de Ibirama × chuva de 3 h na cidade (efeito de remanso) |
| Hora do dia | seno e cosseno da hora (ciclo diário) |

**Lacunas nas janelas de chuva:**

- **1, 3 e 6 h:** exigem todas as horas. Se faltar uma, o valor fica desconhecido.
- **12 h ou mais:** toleram até 10% de horas faltando. Nesse caso a soma é **reescalada** pela cobertura (`soma × janela ÷ horas com dado`).

O motivo é prático: uma única hora com poucas leituras não pode apagar a previsão por um dia inteiro. Isso aconteceu em 22/10 com a estação de José Boiteux, e por isso a regra foi ajustada.

### 6.3 Modelo

- **Ridge**, uma regressão linear com regularização, sobre variáveis padronizadas (média 0, desvio 1).
- A força da regularização (`alpha`) é escolhida automaticamente entre 0,1 e 1.000.000, por validação **em ordem temporal**. O motivo: com poucas semanas de dado, um modelo pouco regularizado "decorava" o treino e errava muito fora dele (medido: 120 cm de erro contra 46 cm da persistência em 12 h).
- Linhas com qualquer variável desconhecida não entram no treino.

### 6.4 Validação honesta (walk-forward)

1. Os dados ficam em ordem de tempo, nunca embaralhados.
2. Fazem-se **5 rodadas**: em cada uma, treina-se com o passado e testa-se no trecho seguinte.
3. Entre treino e teste há um intervalo de *h* horas, para o alvo do treino não "enxergar" o período de teste.
4. Em cada rodada o modelo é comparado com dois concorrentes simples:
   - **persistência**: variação zero;
   - **tendência**: a taxa das últimas 3 h continua por *h* horas.
5. A medida principal é o **RMSE**, o erro quadrático médio, em cm.

### 6.5 Critério de publicação (RN07)

Um horizonte só é **publicado**, e só então aparece na tela, se:

1. o modelo errar **pelo menos 5% menos** que a persistência; **e**
2. houver dias suficientes de dado completo. O valor da RN07 é **60 dias**, mas está **temporariamente em 45** para a demonstração.

Se não passar, a tela diz que a previsão está indisponível e por quê. Exemplo de hoje: "erro de 45,20 cm contra 45,90 cm de quem apenas repete o nível atual". **Nada é inventado.**

O `treinador` retreina todo dia às 07:00 UTC, e a publicação liga ou desliga sozinha conforme o resultado.

### 6.6 Situação atual dos modelos publicados (22/10/2026)

| Estação | 1 h | 3 h | 6 h | 12 h | 24 h |
|---|---|---|---|---|---|
| Rio dos Índios | **2,44 cm** (persist. 5,59) | **10,07 cm** (15,67) | **24,12 cm** (28,41) | não publicado | não publicado |
| Ibirama | não publicado | **7,96 cm** (9,80) | **14,98 cm** (17,35) | não publicado | não publicado |
| José Boiteux | **2,72 cm** (3,84) | **9,43 cm** (10,73) | não publicado | não publicado | não publicado |

Os valores são o RMSE do modelo, com o da persistência entre parênteses. A tela Previsão mostra hoje **só o Rio dos Índios** (veja Limitações).

### 6.7 Como uma previsão é montada na hora

1. O sistema pega os últimos 8 dias de leituras, agrega por hora e monta as variáveis.
2. Usa a **última hora completa**, sem nenhuma variável desconhecida. Se ela tiver mais de **3 h**, a previsão fica indisponível: "Sem dados recentes o bastante para estimar agora".
3. Para cada horizonte publicado:
   - **variação** = saída do modelo (cm);
   - **nível previsto** = nível atual + variação ÷ 100;
   - **incerteza (95%)** = ± 1,96 × σ, onde σ é o desvio dos erros na validação (ou o RMSE, se o desvio não estiver disponível);
   - **faixa prevista** = classificação do nível previsto pelos limites da seção 3.1.
4. **Extrapolação:** o sistema confere se alguma variável de hoje está **fora da faixa vista no treino** (por exemplo, uma chuva maior que qualquer chuva do histórico). Se estiver, a previsão sai marcada, porque o modelo está "chutando" fora do que conhece.

---

## 7. Simulação de chuva ("E se chover X mm?")

A simulação responde a uma pergunta hipotética: **"e se, nas últimas N horas, tivesse chovido X mm em cada ponto, o que o modelo diria sobre o nível?"** Ela **não grava nada** e **não gera alerta**.

### 7.1 Entrada

- **Chuva em mm, por ponto, entre 0 e 400 mm:** Presidente Getúlio (cidade), Dona Emma, José Boiteux, Witmarsum e Vitor Meireles. Campo vazio significa "manter a chuva real".
- **Duração da chuva (janela N):** 1, 3, 6, 12 ou 24 horas.

### 7.2 Cálculo, passo a passo

1. **Parte da situação real de agora:** a mesma linha de variáveis da previsão normal (seção 6.7), com o nível real, a tendência real e os rios vizinhos reais.
2. **Substitui só a chuva dos pontos informados**, supondo que ela caiu **de forma uniforme** ao longo das N horas. Para cada janela de chuva *w* da variável:
   - se *w* ≤ N: `chuva_w = X × w ÷ N` (a fração da chuva que cai dentro dessa janela);
   - se *w* > N: `chuva_w = máximo(chuva real na janela w, X)`. A janela longa contém toda a chuva do cenário e nunca fica com menos do que já choveu de verdade.
3. **Recalcula as interações** (Dona Emma × Boiteux em 6 h; Ibirama × cidade em 3 h).
4. **Nível, tendência e rios vizinhos não mudam.** O cenário mexe só na chuva.
5. **Aplica os mesmos modelos publicados** (seção 6.7) e devolve nível previsto, intervalo de 95%, faixa e o aviso de extrapolação.

### 7.3 Exemplo numérico

O cenário é "30 mm em Dona Emma, em 6 horas":

| Variável | Valor no cenário | Conta |
|---|---|---|
| `chuva_emma_1h` | 5 mm | 30 × 1 ÷ 6 |
| `chuva_emma_3h` | 15 mm | 30 × 3 ÷ 6 |
| `chuva_emma_6h` | 30 mm | 30 × 6 ÷ 6 |
| `chuva_emma_12h` | máx(real, 30) | janela maior que 6 h |
| `chuva_emma_24h` … `168h` | máx(real, 30) | idem |
| `emma_x_boiteux_6h` | 30 × chuva real de 6 h em Boiteux | interação recalculada |

Os demais pontos e o nível ficam como estão. Se o modelo de 3 h devolver, por exemplo, **+18 cm** com o rio em 1,66 m, o nível simulado em 3 h é **1,84 m**, com a faixa de ± 1,96 σ desse horizonte.

### 7.4 Como interpretar

- O resultado mostra **o que o modelo aprendeu**, não uma simulação física do rio (hidráulica, relevo, solo).
- Chuvas muito maiores que as do histórico de treino saem marcadas como **extrapolação**. O histórico atual tem poucos meses e nenhuma cheia grande, então nesses casos o número é pouco confiável.
- Como o modelo é linear, dobrar a chuva aproximadamente dobra o efeito previsto. Um rio real responde de forma não linear: o solo saturado escoa mais, e o transbordamento muda a dinâmica.
- Só aparecem os horizontes **publicados** (hoje 1, 3 e 6 h no Rio dos Índios).

---

## 8. Telas

| Tela | Rota | Conteúdo |
|---|---|---|
| Painel | `/` | Nível atual, faixa, tendência, gráfico do nível, chuva acumulada nos pontos acima da cidade |
| Previsão | `/previsao` | Previsão por horizonte com margem de erro; simulador de chuva |
| Mapa | `/mapa` | Registros da população (6 h a 1 ano), curtir e denunciar |
| Registrar | `/registrar` | Formulário de alagamento |
| Avisos | `/avisos` | Inscrição por e-mail e por notificação no celular |
| Como funciona | `/como-funciona` | Explicação para o público, cores das faixas, análise de correlação |
| Qualidade | `/qualidade` | Situação de cada fonte e cobertura de cada estação |
| Relatório | `/relatorio` | Relatório imprimível (7 ou 30 dias) |
| Moderação | `/moderacao` | Fila de registros, só para quem modera |

Os textos usam linguagem simples, e a cor nunca vem sozinha: toda faixa tem ícone e palavra. Há tema claro e escuro, e o layout foi revisado em celular e desktop.

---

## 9. Limitações até o momento

### Dados

1. **Ribeirão Revólver não tem série pública de nível.** A estação existe na lista da Defesa Civil, mas não devolve leituras. Não há forma honesta de estimar o nível dele; o caminho é pedir a série à Defesa Civil municipal (PE06).
2. **Histórico curto.** A fonte REST guarda dados só desde 03/07/2026, cerca de 3,5 meses, e nesse período **não houve cheia grande**. O modelo nunca viu um evento como o de dezembro de 2020.
3. **Lacunas da fonte:** existem buracos que a própria Defesa Civil não tem, como 12 a 14/08, e esses não podem ser recuperados.
4. **A chuva ERA5 é uma grade grossa.** O ponto do Revólver cai na mesma célula da cidade, então os valores são idênticos. Serve para histórico longo, não para detalhe local.
5. **Limites das faixas:** os do Índios e do Revólver aguardam confirmação oficial (PE05). Ibirama e José Boiteux não têm limites.

### Previsão e simulação

6. **12 h e 24 h não são publicados:** o modelo ainda não vence a persistência nesses horizontes.
7. **O mínimo de dias está em 45, não nos 60 da RN07.** É temporário, para a demonstração, e deve voltar a 60.
8. **O retreino diário cobre só o Rio dos Índios.** Os modelos de Ibirama e José Boiteux foram treinados uma vez e não são revistos, então a publicação deles não se desliga sozinha. Já foi medido que Boiteux 3 h e Índios 6 h hoje não passariam no critério.
9. **A tela Previsão mostra só o Rio dos Índios**, embora a API já tenha previsões publicadas de Ibirama e José Boiteux.
10. **As variáveis foram desenhadas para o Rio dos Índios.** Para outras estações, a chuva "local" continua sendo a da cidade e as interações não fazem o mesmo sentido.
11. **O modelo é linear e não físico.** A resposta a chuvas extremas é a parte menos confiável, e por isso existe o aviso de extrapolação.
12. **A simulação supõe chuva uniforme na janela.** Uma tempestade concentrada em 1 h dentro de uma janela de 6 h é tratada como chuva constante.
13. **Sem dado recente (mais de 3 h) não há previsão.** Uma falha na coleta também desliga a previsão até os dados voltarem.

### Avisos e registros

14. **Ninguém é avisado quando chega um registro novo.** Quem modera precisa abrir `/moderacao` por conta própria. Hoje existe só um usuário (admin).
15. **O push só funciona no app publicado e instalado.** No iPhone é obrigatório adicionar à tela inicial.
16. **O e-mail em desenvolvimento vai para o Mailpit.** O envio real exige configurar um SMTP.
17. **Curtidas e denúncias são anônimas e por navegador.** Quem limpa os dados do navegador ou usa outro aparelho pode reagir de novo. O limite por IP (60 por hora) reduz, mas não elimina, a manipulação.
18. **O limite de requisições é por instância da API.** Com várias instâncias, o limite efetivo é maior.

### Operação

19. **O repositório está no iCloud Drive.** Por isso não se usam *bind mounts* no Docker (eles travam o Docker Desktop), e o ambiente virtual do Python fica fora da pasta.
20. **Testes de ponta a ponta e de acessibilidade (Playwright)** exigem `npx playwright install` antes de rodar.

---

## 10. Próximos passos sugeridos

1. Fazer o `treinador` retreinar todas as estações com nível (Índios, Ibirama, Boiteux) e aumentar a janela de treino.
2. Colocar na tela Previsão a escolha da estação, mostrando "sem faixa oficial" quando faltarem limites.
3. Voltar o mínimo de dias para 60 assim que o histórico permitir.
4. Avisar a moderação por e-mail quando chegar um registro novo.
5. Obter da Defesa Civil a série do Ribeirão Revólver e as cotas oficiais de Ibirama e José Boiteux.
6. Usar os registros validados da população para calibrar quais níveis do rio correspondem a alagamento em cada rua.

---

## Referências no repositório

- Especificação completa: [especificacao-completa.md](especificacao-completa.md)
- Fontes de dados: [fontes-de-dados.md](fontes-de-dados.md)
- Decisões (ADR): [adr/](adr/), em especial [0004, primeiros resultados do modelo](adr/0004-modelo-de-previsao-primeiros-resultados.md)
- Publicação, backup e restauração: [publicacao.md](publicacao.md)
- Código: `desenvolvimento/backend/services/modelo/src/modelo/` (variáveis em `features.py`, treino em `treino.py`, simulação em `inferencia.py`)
