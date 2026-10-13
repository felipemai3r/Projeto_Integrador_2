# ADR 0003: correlação defasada, método e primeiros resultados

Data: 13/10/2026. Atende RF13 (estágio 1 do modelo analítico, seção 9.3 da especificação). Código em `desenvolvimento/backend/services/modelo`.

## Pergunta

Que ponto de influência antecipa a subida do rio dos Índios na cidade, e com quantas horas?

## Método

- **Resposta:** variação horária do nível em Presidente Getúlio, em cm (diferença de médias horárias). Diferenciar evita correlação espúria entre duas séries que só sobem juntas.
- **Explicativa:** chuva acumulada em janela de 3 h terminando `d` horas antes, com `d` de 1 a 36. Só olha o passado.
- **Medida:** correlação de Spearman (a chuva tem cerca de 90% de horas zeradas e cauda longa).
- **Dado:** chuva por hora somando os incrementos de 5 minutos; nível por hora com pelo menos 6 leituras. Hora com cobertura baixa é desconhecida, não zero. Cerca de 1.900 horas válidas por ponto (90 dias).
- **Significância:** teste de permutação cíclica da estatística "maior r entre as 36 defasagens", com p-valor. Um intervalo de confiança do máximo seria sempre positivo (vício de escolher o melhor de 36), e isso foi detectado pelos próprios testes do método antes do uso: o IC por bootstrap do máximo dava "sinal" até em ruído puro.
- **Três análises:** (1) chuva em cada ponto contra a subida do nível; (2) chuva a montante **descontada a chuva local** (regressão em postos com a chuva local nas defasagens 0 a 3 h, e correlação dos resíduos); (3) subida do nível nos outros rios contra a subida na cidade.

## Resultados (90 dias, 15/07 a 13/10/2026, janela de 3 h)

| Análise | Resultado |
|---|---|
| 1. Chuva por ponto | Todos os seis pontos mostram relação (r de 0,34 a 0,42, p ≤ 0,005), todos na menor defasagem possível, 1 h |
| 2. Chuva a montante sem a local | O efeito adicional some ou fica fraco: Dona Emma r 0,13 (p 0,10), Witmarsum 0,12 (p 0,16), José Boiteux 0,07 (p 0,46), Vitor Meireles 0,15 (p 0,055). Só Ibirama, que fica a **jusante**, passa de p 0,05 (r 0,17) |
| 3. Nível em outros rios | Ibirama r 0,36 em 1 h (10 km abaixo, mesma bacia, responde junto); José Boiteux r 0,14 em 2 h (p 0,02) |

O p-valor de Vitor Meireles está na fronteira (0,055 com 200 permutações e 0,0495 com 100): os valores de p variam cerca de 0,01 conforme o número de permutações, então tratar p entre 0,04 e 0,07 como "indeterminado".

A chuva é fortemente colinear entre as estações (Spearman de 0,53 a 0,77), porque a mesma frente passa por todas. Por isso o resultado 1 sozinho engana: todos "antecipam" o rio.

## Interpretação honesta

1. **O rio dos Índios responde à chuva local em 1 hora ou menos.** A bacia é pequena e rápida. A defasagem de 1 h é o limite inferior da análise horária, não um tempo de viagem de chuva vinda de montante.
2. **Nesta base não há evidência de que a chuva a montante antecipe a subida na cidade** além do que a chuva local já explica. O resultado não prova que não existe: são 90 dias com poucos eventos fortes (limitação declarada na seção 9.5) e resolução horária.
3. **A hipótese do coordenador (combinação de Dona Emma e José Boiteux) não foi confirmada nem refutada.** Ela é sobre efeito conjunto e sobre remanso (nível do Itajaí do Norte barrando o afluente), que exigem eventos fortes e o teste de interação do estágio 2. Os dados atuais não têm esses eventos.
4. A correlação entre níveis (análise 3) mostra que o José Boiteux antecipa a cidade em cerca de 2 h, com efeito fraco (r 0,14). É um sinal a acompanhar, não uma conclusão.

## Próximos passos

- Repetir a análise a cada semana: a base cresce e os eventos fortes acumulam.
- Resolução de 15 minutos para medir a defasagem local (hoje presa em 1 h).
- Estágio 2: regressão com termo de interação (Dona Emma × José Boiteux) e nível do Itajaí do Norte, testando o remanso.
- Pedir à Defesa Civil a lista de eventos (PE07): eventos rotulados valem mais que qualquer volume de dia seco.

## Resultado como produto

`GET /api/correlacao` devolve a última rodada com a leitura em linguagem simples ("sem relação clara nesta base: o acaso explica o resultado"). A interface pública mostrará exatamente essa honestidade, sem prometer previsão.
