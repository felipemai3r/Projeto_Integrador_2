# Padrões de tela, estados e voz

Como os componentes se compõem nas telas do sistema (`docs/arquitetura-desenvolvimento.md`, seção 8) e o que cada tela é obrigada a tratar.

---

## Navegação
- **Celular:** barra inferior fixa com 4 destinos (Painel, Previsão, Mapa, Avisos). Simulação e Registro de ocorrência abrem a partir do Painel e da Previsão. Administração só pelo desktop e atrás de login.
- **Desktop:** barra lateral estreita ou superior; Painel em grade 12 colunas, StationCards lado a lado.
- Qualquer informação de risco a no máximo 2 toques da tela inicial (RNF08).

## Anatomia da tela inicial (Painel, CDU01)
Ordem vertical no celular, tudo legível em 360×640 sem rolar até o primeiro cartão:
1. `Header` (marca) + `AlertBanner` se houver alerta vigente.
2. Um `StationCard` por estação alvo (Rio dos Índios, Ribeirão Revólver).
3. `SeriesChart` do histórico recente com `SegmentedControl` de período.
4. `RainAccumulatedTable` dos pontos de influência.
5. Chamadas: "Ver previsão", "Simular chuva", "Registrar alagamento" (CTA com destaque laranja, único).
6. `OfficialNotice`.

## Estados obrigatórios (toda tela de dado)
| Estado | Comportamento |
|---|---|
| Carregando | `Skeleton` nos blocos; sem spinner de tela cheia; o casco do app (PWA) abre na hora |
| Normal | Dado com `SourceStamp` |
| Desatualizado | Último dado válido + `StaleNotice` + `RiskBadge` cinza; **não** gera alerta (RN04) |
| Indisponível | Mensagem humana e o que fazer ("Tente de novo em alguns minutos"); outras estações seguem normais |
| Sem previsão (RN07) | "A previsão ainda não está disponível. Precisamos de mais dados para estimar com segurança." + painel observado continua |
| Offline | Faixa "Você está sem internet. Mostrando a última leitura de HH:MM". Casco em cache, **dado ao vivo nunca vem de cache como se fosse atual** |
| Erro | Texto claro, botão "Tentar de novo", sem código técnico exposto |
| Vazio | Explica por quê e oferece ação (ex.: mapa sem ocorrências validadas) |

## Voz e microcopy

**Princípios:** simples, calmo, direto, honesto sobre incerteza.

| Em vez de | Escreva |
|---|---|
| "Cota de 4,62 m" | "Nível do rio: 4,62 m" (com explicação em "o que é isso?") |
| "Inundação iminente!" | "O rio está subindo 12 cm por hora." |
| "Vai alagar a rua X" | "Se a chuva continuar assim, o nível pode chegar a 5,10 m em 6 horas." |
| "Erro 500" | "Não conseguimos carregar agora. Tente de novo." |
| "Clique aqui" | "Registrar alagamento" |

**Textos fixos:**
- Aviso oficial: "Estimativa de apoio. A fonte oficial é a Defesa Civil de Presidente Getúlio."
- Cenário: "Cenário hipotético. Não é uma previsão."
- Desatualizado: "Dado desatualizado. Última leitura boa às {hora}."
- Push (título, até 50 caracteres): "Rio dos Índios em atenção" · corpo: "Nível em 4,62 m, subindo. {Observado|Previsão}. Fonte oficial: Defesa Civil." · sempre com link para o painel.
- Encerramento de alerta (CDU07 A2): "Rio dos Índios voltou ao normal. Nível em 3,80 m."

**Evite:** caixa alta, exclamação, "URGENTE", jargão (remanso, hidrograma, RMSE) na interface pública. Termos técnicos ficam na página "Como funciona" e na área administrativa.

## Mapa e ocorrências
- Base OpenStreetMap via Leaflet. Estações com ícone próprio e o `RiskBadge` no popup.
- Ocorrências: ícone por tipo de impacto + forma por status (pendente = contorno tracejado, validada = preenchido). Lista equivalente ao mapa para leitores de tela.
- Registro: no máximo 4 passos, "Está acontecendo agora" preenche data e hora (CDU04 A2). Anônimo, sem identificação do autor (RN06, RNF15).

## Gráfico de previsão (RF19)
- Eixo X em horário local de Brasília (America/Sao_Paulo), 24h. Linha vertical "agora" separa passado e futuro.
- Passado: linha cheia. Futuro: tracejada com faixa de incerteza. Cenário: tracejada laranja com selo.
- Limiares como linhas horizontais rotuladas com a faixa e o valor em metros.

## Acessibilidade por tela (mínimo)
- Landmarks (`header`, `nav`, `main`), um `h1` por tela, títulos em ordem.
- Anúncio de mudança de faixa por `aria-live="polite"`; alerta novo por `role="alert"` uma única vez.
- Todo gráfico com resumo textual ("Nível subiu de 3,10 m para 4,62 m nas últimas 6 horas") e tabela.
- Teste manual obrigatório antes de cada entrega: teclado, leitor de tela (VoiceOver), zoom 200%, modo noite, 360px.

## PWA e aparência instalada
- `manifest.webmanifest`: `display: standalone`, `theme_color` = `brand-marinho` (#063265), `background_color` = superfície base do modo dia, ícones 192/512 e maskable.
- Barra de status e `theme-color` seguem o tema (duas metas, uma por esquema de cor).
- Ícone do app: farol/gota estilizado em azul Defesa com filete laranja. Arte final é uma entrega do Sprint de design (pendente).
