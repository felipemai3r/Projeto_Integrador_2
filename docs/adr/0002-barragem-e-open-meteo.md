# ADR 0002: barragem normalizada, previsão de chuva e histórico ERA5

Data: 12/10/2026.

## Decisões

- **Barragem Norte em altura sobre o fundo.** `/api/barragens` entrega a cota absoluta (273,95 m) e a série REST entrega a altura sobre o fundo (17,95 m). Confirmado que `cota − 256 = altura` no mesmo instante. Tudo é gravado como `reservatorio_m` (altura), mais `reservatorio_pct` e o estado das três comportas (`comporta_galeria`, `comporta_tulipa258`, `comporta_tulipa264`, valor 1 aberta ou 0 fechada).
- **Previsão de chuva** do Open-Meteo (`best_match`, 3 dias, horária, com probabilidade) para todas as estações ativas, a cada hora, em `previsao_chuva`. `gerado_em` é a hora cheia da coleta, o que preserva a série de previsões para avaliar o erro depois.
- **Histórico ERA5** (Open-Meteo Archive) gravado como `chuva_h001_mm` da fonte `openmeteo_archive`, de 01/11/2020 até 6 dias atrás (a fonte tem defasagem de cerca de 5 dias). Cobre o evento de dezembro de 2020.
- **Canário de contrato** diário às 09:00 UTC para as quatro fontes, com log de erro quando a estrutura mudar.

## Medição que confirma a limitação LD04

Em 17/12/2020 a ERA5 indicou **52,6 mm em 24 h** para a estação de Presidente Getúlio (pico horário de 21,1 mm). O município relata cerca de 120 mm em 6 horas naquele evento. A reanálise subestima o pico em mais de duas vezes. Uso permitido: contexto e regime de chuva. **Não usar como rótulo nem como verdade de campo**, e nunca calibrar limiar de alerta com ela.

## Observação

DCSC-00174 (Revólver) herda a série ERA5 de Presidente Getúlio porque as coordenadas são próximas (grade de cerca de 25 km). Isso não é dado do Revólver e não deve alimentar o modelo daquela estação.
