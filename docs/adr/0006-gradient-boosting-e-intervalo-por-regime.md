# ADR 0006: gradient boosting, janela longa no rio dos Índios e intervalo de previsão por regime de chuva

Data: 05/11/2026. Revisa o modelo do ADR 0004 e a seção 4 do ADR 0005 (janela de treino do rio dos Índios). **Não altera a RN07**: o critério de publicação continua sendo vencer a persistência por 5% na validação walk-forward, com 60 dias de dado útil. Código em `desenvolvimento/backend/services/modelo` (`treino.py`, `features.py`, `treinar.py`, `inferencia.py`, `registry.py`) e `api/src/api/previsao.py`.

## Contexto

Com 14 meses de séries do painel municipal (ADR 0005), o Ridge do ADR 0004 passou a ser o gargalo:

- **Em 24 h o Ridge perde para a persistência** (razão 1,46), e em 12 h ganha por pouco.
- **O intervalo era `previsto ± 1,96 × desvio global dos resíduos`.** Em 6 h dava ±40 cm até em tempo seco, onde o modelo erra muito menos, e é estreito demais na enchente.

Os experimentos abaixo usam o mesmo teste para todas as variantes: últimos 100 dias, 5 blocos walk-forward, treino só com o passado, `gap` = horizonte.

## Evidência

RMSE em cm da variação do nível (entre parênteses, a razão contra a persistência; menor é melhor):

| Horizonte | Ridge atual (120 dias) | HistGradientBoosting, 14 meses, pontos de série longa |
|---|---|---|
| 6 h | 18,7 (0,81) | 16,2 (0,70) |
| 12 h | 32,9 (0,89) | 32,5 (0,88) |
| 24 h | 73,2 (1,46) | 46,6 (0,93) |

A variante escolhida (gradient boosting, `pontos_chuva` do rio dos Índios com as serras e o Revólver, sem Boiteux e Ibirama, mais as variáveis de tendência e faixa de 24 h) dá, na razão contra a persistência:

| Horizonte | 3 h | 6 h | 12 h | 24 h |
|---|---|---|---|---|
| Razão (variante escolhida) | 0,59 | 0,69 | 0,86 | 0,87 |

Incluir Boiteux, Vitor e Ibirama (só ~4 meses de série, NaN no resto do período) **piorou** 12 h (0,93) e 24 h (1,00 da persistência).

**Intervalo.** Hoje o intervalo é `± 1,96 × desvio global dos resíduos`: em 6 h dá ±40 cm (80 cm de largura total) mesmo em tempo seco. Com quantis empíricos dos resíduos por regime de chuva, em 6 h:

| Regime | Largura total do intervalo |
|---|---|
| seco | 18 cm (cobertura de 95%) |
| chuva | 119 cm |
| chuva forte | 150 cm |

Em 12 h e 24 h, com quantis 2,5/97,5, a cobertura caiu para 92 a 93%: a chuva futura não é conhecida, então o erro cresce no trecho final. Por isso o nível do quantil é calibrado (decisão 4).

## Decisões

### 1. Modelo (`treino.py`)

`HistGradientBoostingRegressor(loss="absolute_error", max_iter=600, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=80, l2_regularization=2.0, early_stopping=False, random_state=0)`, construído num único ponto (`novo_pipeline`).

- **Sem early stopping**: o padrão `auto` o liga sozinho acima de 10 mil linhas e separaria uma fatia aleatória do treino, quebrando a ordem temporal. Com a semente fixa, o mesmo dado gera o mesmo modelo.
- A validação walk-forward (`TimeSeriesSplit(n_splits=5, gap=h)`), os baselines (persistência e tendência) e a RN07 ficam **como estão**. `DIAS_MINIMOS` volta a 60 (o valor da RN07; o 45 era temporário da demonstração).
- **O modelo aceita NaN.** `preparar` passa a exigir só o alvo e as colunas obrigatórias `nivel_m`, `taxa_1h_cm`, `taxa_3h_cm_h`; as demais podem ser NaN (hora sem leitura continua sendo NaN, nunca zero). Em cada ajuste (cada dobra e o final) saem as colunas com menos de 50 valores não nulos no treino daquele ajuste, porque o HGB quebra com coluna vazia; o modelo final guarda a lista de colunas que de fato usou. As obrigatórias nunca saem.

### 2. Variáveis (`features.py`)

- Novas, a partir do nível do alvo e só com o passado: `taxa_6h_cm_h`, `taxa_24h_cm_h`, `nivel_min_24h_m` e `nivel_max_24h_m` (janela de 24 h com no mínimo 18 horas de dado). O teste de não vazamento cobre as quatro.
- **Rio dos Índios (`DCSC-00043`)**: chuva de `DCSC-00043`, `DCSC-00037`, `DCSC-00015`, `DCSC-00174`, `DC-PEU-003`, `DC-PEU-004` e `DC-PEU-002`; **sem vizinhos de nível** e **sem as interações explícitas** (o gradient boosting modela interações sozinho); `janela_dias=None`, ou seja, todo o histórico desde 13/09/2025. O rótulo de cada ponto continua vindo de `PONTOS_CHUVA`.
- O Revólver (`DCSC-00174`) mantém seus pontos e seu vizinho de nível, e o histórico completo. Estação fora de `ALVOS` continua com o conjunto e as interações antigos.

### 3. Por que Boiteux e Ibirama saíram do 00043 por ora

Boiteux (chuva e nível), Vitor e Ibirama só têm ~4 meses de série (API REST), com NaN no resto do período. Na mesma validação, incluí-los piorou 12 h (0,93) e 24 h (1,00): o modelo aprende o padrão da janela curta e o aplica ao período inteiro. A hipótese central do coordenador (Dona Emma × Boiteux) e o remanso do Ibirama **ficam em aberto**, sem evidência a favor nem contra. **Voltar a testar quando essas séries tiverem pelo menos 1 ano**, ou quando entrarem por outra fonte. Isso substitui o item "janela longa pendente" da seção 4 do ADR 0005.

### 4. Intervalo por regime, calibrado (`treino.py`)

Usa os resíduos fora da amostra das 5 dobras (`res = real − previsto`, em ordem temporal).

- **Regime de cada linha**: `m` = maior valor entre as colunas `chuva_*_6h` da linha (só as que existem no modelo). `seco` se `m < 1 mm`; `chuva` se `1 ≤ m < 10`; `chuva_forte` se `m ≥ 10` **ou se todas forem NaN** (sem saber se chove, o lado conservador).
- **Escolha do nível**: para os alfas candidatos `(0,025; 0,015; 0,01; 0,005; 0,0025)`, calibram-se os quantis `alfa` e `1 − alfa` por regime nos **primeiros 60%** dos resíduos (regime com menos de 30 resíduos usa os quantis de todos) e mede-se a cobertura nos **últimos 40%**. Fica o primeiro alfa com cobertura total ≥ 95% (se nenhum, o menor). Com o alfa escolhido, os quantis por regime são recalculados com **todos** os resíduos.
- Guardado em `Resultado`, nos metadados do registro e no artefato: `intervalo_por_regime = {regime: [lo_cm, hi_cm]}`, `alfa_intervalo`, `cobertura_validacao`, `colunas_obrigatorias` e o marcador `aceita_nan=True`. `desvio_residual_cm` continua gravado (compatibilidade).

### 4.1 Nível de confiança por horizonte (decidido após a primeira verificação)

Com 95%, o intervalo de 12 h e 24 h ficou largo demais para orientar mesmo com tempo seco (122 cm e 269 cm de largura total na verificação abaixo), porque nesses horizontes o erro é dominado pela chuva que ainda vai cair, que o modelo não conhece. Nos experimentos (últimos 100 dias), a largura com tempo seco foi:

| Horizonte | 95% | 90% | 80% |
|---|---|---|---|
| 6 h | 18 cm | 10 cm | 6 cm |
| 12 h | 63 cm | 30 cm | 19 cm |
| 24 h | 152 cm | 91 cm | 42 cm |

Decisão: **95% até 6 h e 80% em 12 h e 24 h** (`CONFIANCA_POR_HORIZONTE` em `treino.py`), o nível usual em boletins de horizonte longo. Os alfas candidatos partem do nominal `(1 − confiança) / 2` e alargam as caudas (×0,6, ×0,4, ×0,2, ×0,1) até a cobertura medida atingir o nível prometido. A API devolve `confianca` em cada horizonte e a tela mostra o nível usado ("80% de confiança"); nunca se promete 95% onde a cobertura real é menor. Modelos antigos seguem com 95% (±1,96σ).

Treino publicado em 06/11/2026 (todo o histórico): 12 h com 80% → alfa 0,06, cobertura 83,3%, largura 12 / 79 / 134 cm (seco / chuva / forte); 24 h com 80% → alfa 0,02, cobertura 86,6%, largura 90 / 227 / 261 cm. Os cinco horizontes do rio dos Índios foram publicados.

### 5. Inferência na API (`api/previsao.py`, `inferencia.py`)

- Se o artefato (ou, na falta, os metadados) tem `intervalo_por_regime`: intervalo = `previsto + [lo, hi]` do regime da linha usada (assimétrico), `incerteza_m = (hi − lo) / 2 / 100`. Na simulação o regime vem da linha **com o cenário aplicado**, então simular chuva forte alarga o intervalo. Sem `intervalo_por_regime` (artefato antigo): `± 1,96 σ`, como sempre.
- `escolher_linha`: se o artefato tem `aceita_nan`, exige só `colunas_obrigatorias` + `nivel_m`. Na mesma hora, prefere a chuva estimada pelos vizinhos à medida quando a estimada deixa menos colunas em branco; empate fica com a medida. Artefato antigo continua exigindo todas as `colunas`.
- Coluna ausente vira NaN, nunca zero; a checagem de extrapolação ignora variável sem valor; no cenário, janela longa sem leitura recebe o valor do cenário (em vez de propagar NaN).

## Verificação no banco real (05/11/2026, sem salvar)

`python -m modelo.treinar --sem-salvar` com o código novo, todo o histórico e as 5 dobras walk-forward sobre ele (não é o recorte de 100 dias dos experimentos, por isso os números diferem). RMSE em cm; "largura" é a largura total do intervalo em seco / chuva / chuva forte.

Rio dos Índios (`DCSC-00043`, ~360 dias úteis):

| Horizonte | Modelo | Persistência | Tendência | Razão | Alfa | Cobertura | Largura (cm) | Publica |
|---|---|---|---|---|---|---|---|---|
| 1 h | 2,6 | 3,7 | 2,9 | 0,70 | 0,025 | 95,7% | 3 / 6 / 26 | sim |
| 3 h | 7,4 | 9,9 | 9,5 | 0,75 | 0,025 | 95,2% | 7 / 25 / 75 | sim |
| 6 h | 13,5 | 17,4 | 20,7 | 0,78 | 0,01 | 96,0% | 23 / 115 / 168 | sim |
| 12 h | 23,5 | 27,2 | 44,5 | 0,86 | 0,005 | 96,0% | 122 / 258 / 264 | sim |
| 24 h | 32,3 | 36,1 | 87,6 | 0,89 | 0,0025 | 94,8% | 269 / 350 / 359 | sim |

Ribeirão Revólver (`DCSC-00174`, ~310 a 330 dias úteis): **nenhum horizonte supera a persistência por 5%** (razões de 0,96 a 1,03; o RMSE do modelo empata com o da persistência, de 2,4 a 9,0 cm), então nada seria publicado. O Revólver não foi alterado nesta mudança além do modelo e das quatro variáveis novas; a avaliação dele é um próximo passo separado.

## Alternativas descartadas

- **Manter o Ridge e só estreitar o intervalo**: não resolve o 24 h (1,46 da persistência).
- **Boiteux, Vitor e Ibirama no 00043**: pioraram 12 h e 24 h (ver decisão 3).
- **Interações explícitas no 00043**: o HGB as aprende; mantê-las só aumentava a lista de colunas.
- **Quantis fixos 2,5/97,5**: a cobertura em 12 e 24 h ficou em 92 a 93%.
- **Intervalo único (desvio global)**: largo demais em tempo seco, estreito demais na enchente.

## Consequências e limitações

- **Em 12 h e 24 h o modelo ainda tem pouca informação do futuro**: a chuva que vai cair nas próximas horas não é variável. O ganho sobre a persistência é pequeno (0,86 e 0,87) e o intervalo precisa ser largo para cobrir. **Próximo passo: o histórico de previsões do Open-Meteo** (ADR 0004, "A chuva prevista não entra"), guardado hora a hora, para a previsão de chuva entrar como variável.
- A cobertura de 95% é medida nos **últimos 40% dos resíduos**, em um período curto e com poucos eventos fortes; o regime `chuva_forte` tem poucos resíduos. A validação continua preliminar para extremos (ADR 0004).
- **Dependência de dados para o 00043**: com a janela longa, o modelo usa o painel municipal e o pluviômetro do Revólver. Se uma fonte ficar fora do ar, a previsão segue com NaN nessas colunas (menos informação, intervalo conservador quando toda a chuva some), em vez de ficar "sem dados recentes".
- **Artefatos antigos continuam funcionando** na API (intervalo `± 1,96 σ`, todas as colunas obrigatórias). Mas as variáveis que a API monta para o 00043 deixam de incluir Boiteux, Ibirama e Vitor: um Ridge antigo do 00043 que dependa delas passa a responder "sem dados recentes" até o retreino publicar o modelo novo no horizonte (o treino diário às 07:00 UTC publica sozinho se a RN07 for atendida).
- Treinar é mais lento (600 árvores por ajuste, 6 ajustes por horizonte); a suíte de testes também.
- O campo `algoritmo` do registro passa a ser `hist_gradient_boosting`; os registros anteriores ficam como `ridge`.
