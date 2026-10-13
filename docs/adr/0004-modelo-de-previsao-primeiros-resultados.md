# ADR 0004: modelo de previsão (estágio 2), validação e critério de publicação

Data: 13/10/2026. Atende CDU02, CDU03, CDU09, CDU12 e RN07. Código em `desenvolvimento/backend/services/modelo` (`features.py`, `treino.py`, `inferencia.py`, `registry.py`).

## O que foi construído

- **Variáveis** (`features.py`): chuva acumulada em 1, 3, 6, 12, 24, 48, 72 e 168 h nos 5 pontos de chuva; nível, taxa e aceleração na cidade; nível e taxa em José Boiteux e Ibirama; interações Dona Emma × José Boiteux (chuva de 6 h) e nível do Ibirama × chuva local de 3 h (testa o remanso); hora do dia (seno e cosseno). Hora sem cobertura é desconhecida, nunca zero. **Nenhuma variável usa dado futuro**: há teste que corta a série em `t`, e outro que adultera o futuro, e comparam a linha de `t`.
- **Alvo:** variação do nível em `h` horas, em cm (1, 3, 6, 12 e 24 h). Prever a variação torna a persistência (variação zero) o baseline natural.
- **Modelo:** Ridge com variáveis padronizadas. O `alpha` é escolhido por validação cruzada **temporal** dentro do treino.
- **Validação:** walk-forward com 5 dobras e intervalo (`gap`) de `h` horas entre treino e teste. Comparação obrigatória com a persistência e com a extrapolação linear da tendência.
- **Publicação (RN07):** só publica se o erro for pelo menos 5% menor que o da persistência **e** houver 60 dias de dado completo. Caso contrário a previsão fica indisponível e a API diz o motivo. O serviço `treinador` retreina todo dia às 07:00 UTC e publica ou revoga sozinho.
- **Simulação:** "e se nas últimas N horas tivesse chovido X mm em cada ponto?", com intensidade uniforme. Janelas de chuva maiores nunca recebem menos do que já choveu. Valores fora do que foi visto no treino marcam `extrapolacao` (confiança baixa).

## Dois erros achados e corrigidos durante a validação

1. **O `RidgeCV` padrão usa *leave-one-out*, que embaralha o tempo.** Com linhas vizinhas quase idênticas, ele sempre prefere pouca regularização, e o erro explodia fora da amostra: 120 cm contra 46 cm da persistência em 12 h. Trocado por validação cruzada temporal (com `gap`).
2. A primeira tentativa de consertar foi só ampliar a grade de `alpha`, o que **não mudou nada**, porque o problema era o critério de escolha, não a grade. Foi medido antes de aceitar.

## Resultados (53 dias de dados completos, RMSE em cm da variação do nível)

| Horizonte | Modelo | Persistência | Tendência | Leitura |
|---|---|---|---|---|
| 1 h | 2,4 | 5,6 | 3,8 | Vence com folga (57% menos erro) |
| 3 h | 10,3 | 15,7 | 13,3 | Vence (34%) |
| 6 h | 23,8 | 28,5 | 30,9 | Vence (16%) |
| 12 h | 43,4 | 46,1 | 69,2 | Empate técnico (6%), na margem mínima |
| 24 h | 73,9 | 64,0 | 142,7 | **Perde** para a persistência |

## Decisão e limitações

- **Nenhum horizonte está publicado hoje**, porque há 53 dias de dado completo e o mínimo é 60 (as variáveis de 168 h consomem a primeira semana). O que se espera, **se a validação se mantiver**: 1, 3 e 6 h publicam por volta de 20/10; 12 h fica na fronteira; 24 h não publica.
- **A validação é preliminar.** São poucas semanas e poucos eventos fortes (a maior variação do nível em 12 h foi de cerca de 2,7 m, mas esses casos foram raros). Um modelo que vence a persistência em dias calmos pode falhar justamente na enxurrada. Antes de divulgar previsão ao público, recomendo conferir o desempenho **nos eventos de subida** (probabilidade de detecção e alarme falso na troca de faixa, seção 9.4 da especificação), o que exige eventos rotulados da Defesa Civil (PE07).
- A chuva **prevista** (Open-Meteo) não entra no treino, porque o histórico de previsões ainda está sendo acumulado. Hoje o modelo só usa o observado. Quando houver meses de previsões gravadas, entra como variável (ganho esperado nos horizontes longos).
- Hora do dia como variável com apenas 3 meses de dado pode capturar acaso; revisar com um ano.
