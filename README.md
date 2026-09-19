# Projeto Integrador II, Sistema de Suporte à Decisão para Enchentes e Enxurradas em Presidente Getúlio (SC)

Repositório da disciplina 75PIN, Projeto Integrador II (UDESC/CEAVI, Engenharia de Software, 2026/2), prof. Pedro Sidnei Zanchett. Equipe: Diogo e Felipe.

O sistema estima o comportamento do rio dos Índios e do ribeirão Revólver, em Presidente Getúlio, a partir da chuva observada e prevista nos pontos de influência a montante, e comunica esse risco para a população e para a Defesa Civil municipal. A base arquitetural é a [RADIAN](docs/radian.md), arquitetura de referência da tese de doutorado do professor (UFSC, 2025).

A pergunta que o sistema responde é operacional e veio do coordenador da Defesa Civil municipal: quando chove forte em Dona Emma e em José Boiteux ao mesmo tempo, a cidade alaga, mas quando chove em apenas um desses pontos o impacto é pequeno. Hoje essa relação não está em nenhum sistema.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Especificação completa](docs/especificacao-completa.md) | Entrega dos itens 15 e 16. Escopo, requisitos, regras de negócio, casos de uso, modelo analítico, riscos e critérios de aceitação |
| [Fontes de dados](docs/fontes-de-dados.md) | Levantamento e validação técnica das APIs, com endpoints testados, retenção medida e pendências de acesso |
| [Arquitetura e desenvolvimento](docs/arquitetura-desenvolvimento.md) | Documento interno de construção: serviços, banco, contêineres, execução local e roteiro de implementação |
| [Estudo da RADIAN](docs/radian.md) | Estrutura da arquitetura de referência e derivação do nível genérico ao específico |

## Situação por fase do plano de ensino

### Fase 1 (15 por cento)

| Aulas | Conteúdo | Situação |
|---|---|---|
| 01 e 02 (06 e 08/08) | Apresentação da disciplina e introdução à RADIAN | Concluído |
| 03 e 04 (13 e 15/08) | Escolha e delimitação do case, definição de equipe | Concluído. Case definido em Presidente Getúlio, ver [contexto](docs/especificacao-completa.md#2-contexto-e-delimitação-do-problema) |
| 05 e 06 (20 e 22/08) | Levantamento de bases de dados e APIs | Concluído, ver [fontes de dados](docs/fontes-de-dados.md) |
| 07 e 08 (27 e 29/08) | Mapeamento das fontes e estratégia de coleta | Concluído. Estratégia em [plano de coleta](docs/fontes-de-dados.md#9-plano-de-coleta) |

### Fase 2 (15 por cento)

| Aulas | Conteúdo | Situação |
|---|---|---|
| 09 e 10 (03 e 05/09) | Estudo da RADIAN e processo de derivação | Concluído, ver [estudo](docs/radian.md) e [derivação aplicada](docs/especificacao-completa.md#4-derivação-da-arquitetura-radian) |
| 11 e 12 (10 e 12/09) | Requisitos funcionais e não funcionais, casos de uso | Concluído, ver [requisitos](docs/especificacao-completa.md#6-requisitos-funcionais) e [casos de uso](docs/especificacao-completa.md#10-casos-de-uso) |
| 13 e 14 (17 e 19/09) | Projeto de arquitetura e recursos de automação | Concluído, ver [arquitetura](docs/arquitetura-desenvolvimento.md) e [modelo analítico](docs/especificacao-completa.md#9-modelo-analítico) |
| 15 e 16 (24 e 26/09) | Entrega da especificação completa e validação de escopo | Documentação pronta para validação, com [pendências listadas](docs/especificacao-completa.md#15-pendências-para-validação) |

### Fases seguintes

Fase 3 é a implementação do sistema, com roteiro definido em [arquitetura e desenvolvimento](docs/arquitetura-desenvolvimento.md#14-roteiro-de-implementação). Fase 4 é o artigo científico de divulgação e a atividade de extensão.

## O que diferencia este sistema do painel municipal existente

O município já opera um painel de monitoramento bom, em `pdc.presidentegetulio.sc.gov.br`, com nível dos rios, rede de pluviômetros, radar, previsão por modelo físico e notificação push. O levantamento desse painel está na [especificação](docs/especificacao-completa.md#3-o-que-já-existe-e-onde-está-a-lacuna).

O projeto se posiciona nas três lacunas que sobraram:

1. A relação estatística entre a chuva nos pontos de influência a montante e a resposta do rio na cidade não é modelada por ninguém hoje.
2. Não existe registro georreferenciado de onde alagou, e o município confirmou que não possui mapeamento de cota por rua. O sistema constrói esse dado com registro participativo da população.
3. A série histórica está se perdendo. A única API pública com série temporal retém cerca de 80 dias, o que torna a coleta contínua uma tarefa urgente e permanente.
