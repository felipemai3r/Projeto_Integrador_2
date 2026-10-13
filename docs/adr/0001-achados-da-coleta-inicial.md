# ADR 0001: achados da primeira coleta real e decisões decorrentes

Data: 12/10/2026. Contexto: primeira execução do ingestor e da carga inicial contra as APIs reais da Defesa Civil de SC.

## Achados

1. **A série de 5 minutos começa em 22/07/2026** (retenção de cerca de 82 dias em 12/10). Foram capturadas 23 a 24 mil leituras por estação e variável. Os dias anteriores já não existem na fonte: perdemos de 01/07 a 21/07 por não ter coletado antes.
2. **DCSC-00174 (Ribeirão Revólver) não existe na operação `Tags_data` nem tem série na REST.** Só aparece no inventário. Hoje o sistema não consegue obter nenhum dado dela por fonte pública. Depende do município (PE06). O painel e o modelo começam pelo Rio dos Índios.
3. **Na REST, a Barragem Norte (DCSC-00042) devolve `rio_nivel_m` com a altura do reservatório**, não de um rio. Já o endpoint `/api/barragens` usa cota absoluta (ex.: 273,95 m). As duas escalas diferem; o adaptador de barragens (próximo passo) precisa normalizar para uma só.
4. O GraphQL `Tags_data` entrega, por estação, o nível e acumulados de chuva por janela (1h a 168h) no instante da leitura. A REST entrega `chuva_acumulada_mm` a cada 5 minutos, com **semântica do acumulado ainda não confirmada** (por evento, por hora, desde um reinício?). Guardamos como a fonte entrega até confirmar.

## Decisões

- Variáveis separadas por origem: `nivel_m`, `chuva_acumulada_mm` (REST, bruta), `chuva_h001_mm` a `chuva_h168_mm` (GraphQL), `reservatorio_m`, `reservatorio_pct`. O serviço `modelo` soma os incrementos de 5 minutos em chuva horária, exigindo 9 de 12 leituras por hora; hora com cobertura menor vira desconhecida (NaN), nunca zero.
- Cota de barragem nunca é gravada como `nivel_m` (`ESTACOES_RESERVATORIO` no adaptador REST).
- Sem PostGIS: latitude e longitude simples; a checagem de município é feita na aplicação (resolve a inconsistência I4 do plano de ação).
- O ambiente virtual de desenvolvimento **não pode ficar dentro do iCloud Drive**: o iCloud marca os arquivos `.pth` como ocultos e o Python 3.13 ou superior os ignora, quebrando instalações editáveis. Usar `~/.venvs/pgetulio`.

- **Sem bind mount no Compose.** Montar um arquivo do repositório (que está no iCloud Drive) dentro de um contêiner travou o Docker Desktop (o contêiner ficou em `Created` e `docker inspect`/`docker rm` deixaram de responder), exigindo reiniciar o Docker. Regra: arquivos entram na imagem com `COPY`; dados em volumes nomeados.
- **`pkill -f` no mesmo comando que o padrão.** Em automações de terminal, `pkill -f "<texto>"` casa com a própria linha de comando do shell e a derruba. Usar o PID salvo ou `pgrep -x`.

## Pendências geradas

- ~~Semântica de `chuva_acumulada_mm`~~: resolvida (incremento de 5 minutos). Não precisa mais perguntar à Defesa Civil de SC.
