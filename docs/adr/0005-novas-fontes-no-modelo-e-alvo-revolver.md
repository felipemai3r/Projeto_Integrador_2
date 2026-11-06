# ADR 0005: novas fontes no modelo, chuva por h001, alvo Ribeirão Revólver e janela de treino

Data: 05/11/2026. Complementa o ADR 0004 (não altera RN07 nem o critério de publicação). Código em `desenvolvimento/backend/services/modelo` (`dados.py`, `features.py`, `treinar.py`, `agendador.py`, `inferencia.py`) e `api/src/api/previsao.py`.

> **Atualização (ADR 0006).** As seções 2 e 4 abaixo descrevem a decisão original para o rio dos Índios (cinco pontos de chuva e janela de 120 dias). O [ADR 0006](0006-gradient-boosting-e-intervalo-por-regime.md) a substitui: o `DCSC-00043` passa a usar todo o histórico, com as serras e o Revólver, sem Boiteux e Ibirama, e o modelo troca o Ridge por gradient boosting. O restante deste ADR (chuva por h001, Revólver, `escolher_linha`) continua valendo.

## Contexto

A API do painel municipal passou a ser coletada a cada 5 min, com histórico desde 13/09/2025 (~14 meses; a API REST estadual só retém ~80 dias). Ela traz:

- chuva de três estações de serra, papel INFLUENCIA: `DC-PEU-003` (Serra dos Índios, cabeceira do rio dos Índios), `DC-PEU-004` (Serra Vencida) e `DC-PEU-002` (Serra Mirador);
- nível e chuva do Ribeirão Revólver (`DCSC-00174`, papel ALVO, limiares 2,50/3,00/3,50 m), que até então não tinha série;
- 14 meses de nível e chuva de `DCSC-00043`, `DCSC-00037` e `DCSC-00015`.

A chuva dessa fonte é a **acumulada na última hora** (`chuva_h001_mm`, janela móvel), não incrementos de 5 min (`chuva_acumulada_mm`). O modelo só sabia somar incrementos.

## Decisões

### 1. Chuva horária com fallback (`dados.chuva_horaria`)

- Hora com cobertura de incremento (≥ 9 de 12 leituras) continua valendo como antes. Só onde ela é NaN entra o h001.
- A chuva da hora de rótulo H (`[H, H+1h)`) é a leitura h001 que **fecha** a hora: a mais tardia em `[H+1h−5 min, H+1h+1 min]`. Sem leitura nessa faixa, NaN (nunca zero).
- **Por que 5 min antes e só 1 min depois.** A cadência é de 5 min: se a leitura exata falhou, a anterior descreve quase a mesma hora. Já a folga para depois só absorve o jitter de segundos do carimbo. Em `features.py` a linha `t` representa o estado ao fim da hora `t` (nível médio e chuva de `[t, t+1h)`), e o alvo é o nível de `t+h`. Aceitar leituras alguns minutos depois de `t+1h` deixaria entrar chuva do início da hora do alvo; com 1 min o excesso é desprezível diante do atraso de horas entre chover e o rio subir, e treino e inferência usam exatamente a mesma regra. Há teste que apaga ou adultera tudo depois de `H+1h+1min` e confere que a hora H não muda.
- **Só fontes medidas.** `chuva_h001_mm` também existe vindo do Open-Meteo (reanálise ERA5, `fonte_id` 5, 52 mil leituras horárias desde 2020 em todas as estações; e previsão). Isso é modelo em grade, não pluviômetro. O fallback usa lista branca de fontes (`dcsc_graphql`, `dcsc_rest`, `pdc_municipal`); sem isso, o ERA5 preencheria silenciosamente as horas sem medição e seria tratado como chuva observada.
- **Duas fontes para a mesma estação** (REST, GraphQL e painel, com segundos de defasagem): no h001 escolhe-se **uma** leitura por hora (a mais tardia da faixa), nunca soma; leituras no mesmo instante exato viram a média.
- **Nível e incremento de chuva: um instante conta uma vez** (`dados.uma_leitura_por_intervalo`). Antes de contar ou agregar, as leituras do ponto são reduzidas a uma por intervalo de 5 min (média do intervalo). Sem isso, GraphQL e painel gravando o mesmo nível com segundos de diferença faziam 3 instantes distintos passarem pelo mínimo de 6 leituras, e a soma de incrementos de duas fontes dobraria. Os mínimos (6 para nível, 9 de 12 para chuva) passam a significar instantes distintos. Com uma fonte só, em cadência de 5 min, nada muda; com várias, a média da hora deixa de ser ponderada pela fonte que grava mais vezes (diferença medida no rio dos Índios: até ~0,2 cm, só nas horas com três fontes).
- **Pico espúrio, só com o passado.** O h001 é soma em janela móvel de 1 h: de uma leitura de 5 min para a seguinte só pode subir o que choveu naquele passo (30 mm em 5 min seriam 360 mm/h). Uma leitura que supera em mais de 30 mm o **máximo das leituras anteriores nos 10 min anteriores** é descartada; acima de 150 mm também (repete a suspeita do ingestor). O critério não usa a leitura seguinte: o filtro dá o mesmo resultado em série completa (treino) e cortada no fim (inferência), e nada de t+5 min entra na decisão (teste de propriedade: `f(serie[:t]) == f(serie)[:t]`). Compromisso: sem a leitura seguinte não se separa pico isolado de degrau; num salto real que se mantém, só a primeira leitura do degrau cai (a seguinte já compara com o valor alto e passa), um atraso de 5 min no pior caso. Chuva forte de verdade sobe poucos mm por passo e não é tocada. Sem leitura anterior a até 10 min (série horária, lacuna) a leitura passa. Ao descartar o pico, a hora usa a leitura anterior, se houver na faixa.
- O índice horário é sempre regular (o `rolling` das variáveis conta linhas).

### 2. Serras e Revólver como pontos de chuva

> **Superado em parte pelo ADR 0006:** o rio dos Índios deixa de ter "exatamente o conjunto de antes" e passa a usar `DCSC-00043`, `DCSC-00037`, `DCSC-00015`, `DCSC-00174` e as três serras, sem Boiteux, Vitor e Ibirama. A decisão original segue abaixo, como registro.

`PONTOS_CHUVA` passa a ser o **registro de rótulos** (`serra_indios`, `serra_vencida`, `serra_mirador`, `revolver` além dos cinco de sempre), fixos por estação. **Quais pontos entram em cada alvo** é propriedade do alvo: `ConfigAlvo.pontos_chuva` (função `features.pontos_chuva(alvo)`). Treino (`treinar`), `montar_features`, inferência (`api/previsao.py`), imputação por vizinhos e simulação (`aplicar_cenario(..., alvo=)`) usam o conjunto do alvo; estação fora de `ALVOS` usa o conjunto padrão.

- **Rio dos Índios (`DCSC-00043`): exatamente o conjunto de antes**, `local`, `emma`, `boiteux`, `witmarsum`, `vitor`, com as mesmas colunas e as mesmas interações. O retreino diário não ganha variável nenhuma (sem este limite, o loop sobre todo o registro acrescentaria 32 colunas, das serras e do pluviômetro do Revólver, sem decisão; teste cobre). Incluir as serras no Índios fica como decisão futura, com validação própria.
- **Revólver (`DCSC-00174`): `local` (DCSC-00043, na cidade), `revolver`, e as três serras.** Dona Emma e Witmarsum (Itajaí do Norte, outra bacia, dezenas de km) ficam de fora pelo mesmo motivo de Boiteux e Ibirama: a bacia responde em 1 a 6 h e a escala é errada; custariam 16 colunas (e linhas completas) para um sinal que a chuva local e a das serras já cobrem. Vitor também. Reavaliar com a validação se o modelo do Revólver não superar a persistência.

**Compatibilidade.** O artefato guarda `colunas`; a inferência só lê essas colunas, então o modelo publicado do rio dos Índios (treinado em 20/10, colunas antigas) segue funcionando sem retreino e sem mudar de resultado (conferido contra o banco: mesmas colunas de chuva, mesma hora; só as de nível mudam por ≤ 0,2 cm, pela deduplicação da seção 1).

**Linha de variáveis por modelo (`escolher_linha`).** A API não escolhe mais uma "linha atual" global com todas as colunas montadas preenchidas (e uma lista de pontos novos tolerados). Para **cada horizonte/artefato**, usa a linha **mais recente** (dentro de `IDADE_MAXIMA_H` = 3 h) em que todas as `colunas` *daquele* modelo (mais `nivel_m`) estão preenchidas, medidas ou estimadas pelos vizinhos; na mesma hora vale a medida antes da estimada. Consequências: uma serra fora do ar não afeta o modelo do Índios (que não a tem) nem o do Revólver que não a usa; Boiteux com lacuna não derruba o Revólver; horizontes diferentes podem usar horas diferentes (`valido_para` de cada um é a sua hora + horizonte; `base_em` é a hora mais recente usada). Se nenhuma hora serve, o horizonte fica "Sem dados recentes", sem erro e sem inventar número. O aviso `chuva_estimada` lista só os pontos estimados que as colunas do modelo realmente usam. Sem horizonte disponível, `base_em`/`nivel_base_m` mostram o último nível observado recente do alvo.

### 3. Alvo Ribeirão Revólver (`DCSC-00174`)

`ALVOS` passa a ser um dicionário de `ConfigAlvo`. O Revólver é bacia urbana pequena que deságua no rio dos Índios dentro da cidade:

- vizinho de nível: **só o rio dos Índios em Presidente Getúlio** (`nivel_getulio_m`, `taxa_getulio_1h_cm`), por poder representar remanso;
- sem Boiteux e Ibirama (propagação de horas a dias, escala errada; o efeito chega via rio dos Índios) e sem as interações Dona Emma × Boiteux e Ibirama × chuva local;
- a chuva usa o conjunto próprio do alvo (seção 2), com as janelas de 1 a 6 h disponíveis; quem pesa mais é decidido pela regularização do Ridge, não imposto à mão;
- `montar_features(alvo=...)` nunca usa o nível do próprio alvo como vizinho (teste).

Não se adicionou física além disso. Mesmos horizontes, mesmo Ridge, mesma validação e mesmo critério de publicação.

### 4. Janela de treino, por alvo

> **Superado pelo ADR 0006:** o rio dos Índios passa a treinar com todo o histórico (`janela_dias=None`), porque Boiteux e Ibirama, que prendiam a janela em 120 dias, saíram do modelo (a série curta deles piorou a validação em 12 e 24 h). A "janela longa pendente" abaixo foi resolvida dessa forma, e não esperando as séries crescerem. A decisão original segue abaixo, como registro.

A janela é propriedade do alvo (`ConfigAlvo.janela_dias`):

- **Revólver (`DCSC-00174`): todo o histórico desde 13/09/2025.** Todas as suas variáveis (chuva local e do Revólver, serras, nível do rio dos Índios em `DCSC-00043`) vêm do painel municipal, com ~14 meses.
- **Rio dos Índios (`DCSC-00043`): continua nos últimos 120 dias.** Boiteux (chuva e nível) e Ibirama (nível) só vêm da API REST, ~80 dias. O treino exige linhas completas, então com janela longa esses pontos cairiam pela regra de cobertura mínima (50%) e o modelo perderia `emma_x_boiteux_6h` (a hipótese central do coordenador) e o remanso do Ibirama. Como a publicação é automática, isso poderia substituir um modelo publicado por outro conceitualmente pior. Por isso o padrão do `DCSC-00043` não muda.
- `--dias N` e `--desde AAAA-MM-DD` (CLI de `modelo.treinar` e do agendador) sobrescrevem o padrão de todos os alvos.
- A janela longa para o rio dos Índios fica **pendente**: só faz sentido quando Boiteux e Ibirama tiverem cobertura equivalente (a série da REST crescer, ou entrarem por outra fonte), ou com outra estratégia (por exemplo, treinar uma variante só com as variáveis do painel e comparar na validação, sem perder o modelo atual).
- O critério de publicação (RN07: superar a persistência em ≥ 5% e ter dado suficiente) não foi alterado.

Mesmo com a janela de 120 dias, a regra de cobertura mínima de 50% (ponto deixado de fora das variáveis e registrado no log) continua valendo como proteção, pois as linhas completas dependem de todas as colunas.

O agendador treina cada alvo isolado: erro em um (sem leituras, banco, dado ruim) é logado e o outro treina.

## Alternativas descartadas

- **Aceitar h001 até 10 min depois de H+1h:** mais leituras aproveitadas, mas vaza chuva do início da hora do alvo.
- **Qualquer `chuva_h001_mm` sem filtro de fonte:** misturaria reanálise ERA5 com pluviômetro.
- **Somar/mesclar as duas fontes:** dobraria chuva; escolher uma leitura por hora é seguro.
- **Revólver com os mesmos vizinhos de nível do rio dos Índios:** mais variáveis sem justificativa física e menos linhas completas.
- **Treinar o Revólver como variante do mesmo modelo:** o nível, os limiares e a escala de resposta são outros.
- **Janela longa para todos os alvos:** custaria ao rio dos Índios as variáveis de Boiteux e Ibirama (ver seção 4). Janela por alvo evita isso.

## Consequências e limitações

- O rio dos Índios segue com 120 dias e não aproveita os 14 meses das séries do painel até que Boiteux/Ibirama tenham histórico maior; é o custo de não perder o remanso e a interação Dona Emma × Boiteux.
- Misturar incremento (jul/2026 em diante) e h001 (antes) na mesma série é uma aproximação: ambos medem a chuva da hora, mas por métodos diferentes, e há diferenças de arredondamento.
- A validação continua preliminar para eventos extremos (ver ADR 0004); mais meses de dado ajudam, mas não substituem eventos rotulados.
- Frontend: a página de previsão ainda fixa `DCSC-00043` como alvo e lista cinco pontos de chuva; exibir o Revólver e as serras na simulação exige ajuste nela (fora do escopo desta mudança).
- O Revólver só é servido quando o primeiro treino atender à RN07; até lá a API responde "indisponível" com o motivo.
