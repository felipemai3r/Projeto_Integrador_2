# Arquitetura e Guia de Desenvolvimento

Documento técnico interno da equipe. Não é a entrega acadêmica, que está em [especificacao-completa.md](especificacao-completa.md). Aqui fica a decisão de construção: como o sistema é montado, como rodar na máquina, o que sobe em contêiner e como o código fica organizado para ser reaproveitado depois.

## Sumário

1. [Decisões de arquitetura](#1-decisões-de-arquitetura)
2. [Visão de serviços](#2-visão-de-serviços)
3. [Estrutura do repositório](#3-estrutura-do-repositório)
4. [Modelo físico de dados](#4-modelo-físico-de-dados)
5. [Serviço de ingestão](#5-serviço-de-ingestão)
6. [Serviço de modelo](#6-serviço-de-modelo)
7. [API](#7-api)
8. [Front-end PWA](#8-front-end-pwa)
9. [Notificação push](#9-notificação-push)
10. [Rodando localmente](#10-rodando-localmente)
11. [Configuração e segredos](#11-configuração-e-segredos)
12. [Testes](#12-testes)
13. [Publicação](#13-publicação)
14. [Roteiro de implementação](#14-roteiro-de-implementação)

---

## 1. Decisões de arquitetura

| Decisão | Escolha | Motivo |
|---|---|---|
| Linguagem do backend | Python 3.12 | O núcleo do sistema é análise de série temporal e modelo estatístico. Pandas, scikit-learn e LightGBM resolvem isso sem esforço adicional |
| Framework de API | FastAPI | Tipagem, documentação automática em OpenAPI e desempenho adequado |
| Banco | PostgreSQL 16 | Volume estimado de 840 mil registros por ano, que é pequeno. Banco relacional simples resolve, com suporte a JSON para payload bruto e a PostGIS para as ocorrências georreferenciadas |
| Front-end | React com Vite e TypeScript | Ecossistema maduro para PWA, com suporte de biblioteca para gráfico e mapa |
| Mapa | Leaflet com OpenStreetMap | Gratuito, sem chave de API, suficiente para marcar ponto e exibir ocorrências |
| Gráficos | Recharts | Integra bem com React e cobre série temporal e faixa de incerteza |
| Empacotamento | Docker e Docker Compose | Exigência prática do RNF12 e do RNF13, e garante que o sistema suba igual na máquina e no servidor da UDESC |
| Separação em serviços | Ingestão, modelo e API separados | Pedido explícito de reaproveitamento. Cada serviço tem responsabilidade única e pode ser extraído para outro projeto |
| Orquestração de tarefas | APScheduler dentro do serviço de ingestão | Suficiente para a escala do projeto. Fila dedicada (Celery, RQ) fica como evolução, se houver necessidade |

Duas decisões que valem justificativa maior:

**Por que não usar fila de mensagens agora.** Kafka ou RabbitMQ resolveriam o desacoplamento entre coleta e processamento, mas acrescentam um componente para operar, monitorar e explicar na banca, sem benefício real na escala atual. A separação por serviço já garante o reaproveitamento. Se o projeto crescer para mais municípios, a fila entra sem reescrever os adaptadores.

**Por que não usar TimescaleDB de saída.** É a escolha natural para série temporal, mas o volume não justifica. PostgreSQL com índice composto em (estação, variável, horário) atende com folga. A extensão pode ser ligada depois sem mudar o modelo de dados.

---

## 2. Visão de serviços

```
                        ┌──────────────────────────┐
   Fontes externas ───► │  ingestor                │
   (DCSC, Open-Meteo,   │  adaptadores + agendador │
    ANA, CEMADEN)       └────────────┬─────────────┘
                                     │ grava
                                     ▼
                        ┌──────────────────────────┐
                        │  db (PostgreSQL)         │
                        │  leituras, ocorrências,  │
                        │  modelos, alertas        │
                        └───┬──────────────────┬───┘
                     lê     │                  │    lê e grava
                            ▼                  ▼
          ┌──────────────────────┐   ┌──────────────────────────┐
          │  modelo              │   │  api (FastAPI)           │
          │  treino e publicação │   │  consulta, simulação,    │
          │  (job agendado)      │   │  ocorrências, alertas    │
          └──────────────────────┘   └────────────┬─────────────┘
                                                  │ HTTP
                                                  ▼
                                     ┌──────────────────────────┐
                                     │  web (React PWA)         │
                                     │  painel, mapa, push      │
                                     └──────────────────────────┘
```

Responsabilidade de cada serviço:

| Serviço | Responsabilidade | Não faz |
|---|---|---|
| `ingestor` | Chamar as fontes, normalizar, validar e gravar leitura. Registrar log de coleta | Não calcula risco nem previsão |
| `modelo` | Montar as variáveis, treinar, validar contra baseline e publicar modelo aprovado | Não atende requisição do usuário |
| `api` | Servir dados, calcular classificação de risco, aplicar modelo publicado, receber ocorrência, disparar alerta e push | Não coleta de fonte externa |
| `web` | Interface, instalação como PWA e permissão de push | Não fala com fonte externa nem com o banco |

O pacote `common` é compartilhado pelos três serviços Python e concentra o acesso ao banco, os modelos de dados e a configuração, para não duplicar código.

---

## 3. Estrutura do repositório

```
.
├── docker-compose.yml
├── docker-compose.override.yml       # ajustes de desenvolvimento
├── .env.example
├── README.md
├── docs/                             # documentação da disciplina
│   ├── especificacao-completa.md
│   ├── fontes-de-dados.md
│   ├── arquitetura-desenvolvimento.md
│   ├── radian.md
│   └── img/
├── db/
│   └── migrations/                   # migrações SQL versionadas (Alembic)
├── services/
│   ├── common/                       # pacote compartilhado
│   │   ├── pyproject.toml
│   │   └── src/common/
│   │       ├── config.py             # leitura de variáveis de ambiente
│   │       ├── db.py                 # engine e sessão SQLAlchemy
│   │       ├── models.py             # entidades ORM
│   │       └── schemas.py            # contratos Pydantic
│   ├── ingestor/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/ingestor/
│   │       ├── main.py               # agendador
│   │       ├── adapters/
│   │       │   ├── base.py           # interface do adaptador
│   │       │   ├── dcsc_graphql.py
│   │       │   ├── dcsc_rest.py
│   │       │   ├── dcsc_barragens.py
│   │       │   ├── openmeteo_forecast.py
│   │       │   ├── openmeteo_archive.py
│   │       │   └── ana_hidroweb.py
│   │       ├── normalize.py          # conversão para o formato interno
│   │       └── quality.py            # validação de plausibilidade
│   ├── modelo/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/modelo/
│   │       ├── features.py           # montagem das variáveis
│   │       ├── correlacao.py         # análise de correlação defasada
│   │       ├── treino.py             # treino por horizonte
│   │       ├── validacao.py          # walk-forward e baselines
│   │       └── registry.py           # publicação e versionamento
│   └── api/
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/api/
│           ├── main.py
│           ├── routers/
│           │   ├── estacoes.py
│           │   ├── leituras.py
│           │   ├── previsao.py
│           │   ├── simulacao.py
│           │   ├── ocorrencias.py
│           │   ├── alertas.py
│           │   └── admin.py
│           ├── services/
│           │   ├── risco.py          # classificação por limiar
│           │   ├── inferencia.py     # aplicação do modelo publicado
│           │   └── push.py           # envio de notificação
│           └── auth.py
└── web/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── public/
    │   ├── manifest.webmanifest
    │   └── sw.js                     # service worker, push e cache
    └── src/
        ├── pages/                    # Painel, Previsao, Simulacao, Mapa, Inscricao
        ├── components/
        ├── hooks/
        └── lib/api.ts
```

---

## 4. Modelo físico de dados

Esquema inicial. As migrações ficam versionadas em `db/migrations` com Alembic.

```sql
-- fontes externas
CREATE TABLE fonte (
    id            SERIAL PRIMARY KEY,
    codigo        TEXT UNIQUE NOT NULL,      -- dcsc_graphql, dcsc_rest, openmeteo_forecast...
    nome          TEXT NOT NULL,
    base_url      TEXT NOT NULL,
    frequencia_s  INTEGER NOT NULL,
    ativa         BOOLEAN NOT NULL DEFAULT TRUE
);

-- estações de medição
CREATE TABLE estacao (
    id              SERIAL PRIMARY KEY,
    codigo          TEXT UNIQUE NOT NULL,     -- DCSC-00043
    nome            TEXT NOT NULL,
    curso_dagua     TEXT,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    papel           TEXT NOT NULL,            -- alvo | influencia | referencia
    fonte_id        INTEGER REFERENCES fonte(id),
    ativa           BOOLEAN NOT NULL DEFAULT TRUE
);

-- leitura individual, núcleo do sistema
CREATE TABLE leitura (
    id              BIGSERIAL PRIMARY KEY,
    estacao_id      INTEGER NOT NULL REFERENCES estacao(id),
    variavel        TEXT NOT NULL,            -- nivel_m | chuva_mm | reservatorio_m | comporta
    valor           DOUBLE PRECISION,
    unidade         TEXT NOT NULL,
    medido_em       TIMESTAMPTZ NOT NULL,
    coletado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fonte_id        INTEGER NOT NULL REFERENCES fonte(id),
    qualidade       TEXT NOT NULL DEFAULT 'ok',  -- ok | suspeita | descartada
    bruto           JSONB,
    UNIQUE (estacao_id, variavel, medido_em, fonte_id)
);
CREATE INDEX idx_leitura_consulta ON leitura (estacao_id, variavel, medido_em DESC);

-- previsão de chuva, separada da leitura observada
CREATE TABLE previsao_chuva (
    id              BIGSERIAL PRIMARY KEY,
    estacao_id      INTEGER NOT NULL REFERENCES estacao(id),
    gerado_em       TIMESTAMPTZ NOT NULL,
    valido_para     TIMESTAMPTZ NOT NULL,
    chuva_mm        DOUBLE PRECISION NOT NULL,
    probabilidade   DOUBLE PRECISION,
    modelo_fonte    TEXT NOT NULL,
    UNIQUE (estacao_id, gerado_em, valido_para, modelo_fonte)
);

-- limiares por estação, versionados
CREATE TABLE limiar (
    id              SERIAL PRIMARY KEY,
    estacao_id      INTEGER NOT NULL REFERENCES estacao(id),
    faixa           TEXT NOT NULL,            -- observacao | atencao | alerta
    valor_m         DOUBLE PRECISION NOT NULL,
    vigente_desde   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    autor           TEXT NOT NULL,
    justificativa   TEXT NOT NULL
);

-- registro de modelo treinado
CREATE TABLE modelo (
    id              SERIAL PRIMARY KEY,
    estacao_id      INTEGER NOT NULL REFERENCES estacao(id),
    horizonte_h     INTEGER NOT NULL,
    algoritmo       TEXT NOT NULL,
    treinado_em     TIMESTAMPTZ NOT NULL,
    amostras        INTEGER NOT NULL,
    rmse_cm         DOUBLE PRECISION NOT NULL,
    mae_cm          DOUBLE PRECISION NOT NULL,
    rmse_persistencia_cm DOUBLE PRECISION NOT NULL,
    publicado       BOOLEAN NOT NULL DEFAULT FALSE,
    caminho_artefato TEXT NOT NULL,
    metadados       JSONB
);

-- estimativa gerada
CREATE TABLE previsao_nivel (
    id              BIGSERIAL PRIMARY KEY,
    estacao_id      INTEGER NOT NULL REFERENCES estacao(id),
    modelo_id       INTEGER NOT NULL REFERENCES modelo(id),
    gerado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valido_para     TIMESTAMPTZ NOT NULL,
    nivel_m         DOUBLE PRECISION NOT NULL,
    incerteza_m     DOUBLE PRECISION NOT NULL,
    origem          TEXT NOT NULL             -- operacional | cenario
);

-- alertas emitidos
CREATE TABLE alerta (
    id              BIGSERIAL PRIMARY KEY,
    estacao_id      INTEGER NOT NULL REFERENCES estacao(id),
    faixa_anterior  TEXT NOT NULL,
    faixa_nova      TEXT NOT NULL,
    severidade      TEXT NOT NULL,
    origem          TEXT NOT NULL,            -- observado | previsto
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    encerrado_em    TIMESTAMPTZ
);

-- inscrições de push
CREATE TABLE inscricao (
    id              BIGSERIAL PRIMARY KEY,
    endpoint        TEXT UNIQUE NOT NULL,
    chave_p256dh    TEXT NOT NULL,
    chave_auth      TEXT NOT NULL,
    estacao_id      INTEGER REFERENCES estacao(id),
    faixa_minima    TEXT NOT NULL,
    criada_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ativa           BOOLEAN NOT NULL DEFAULT TRUE
);

-- ocorrências informadas pela população
CREATE TABLE ocorrencia (
    id              BIGSERIAL PRIMARY KEY,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    ocorreu_em      TIMESTAMPTZ NOT NULL,
    tipo_impacto    TEXT NOT NULL,            -- via_intransitavel | agua_calcada | agua_imovel | outro
    descricao       TEXT,
    foto_path       TEXT,
    status          TEXT NOT NULL DEFAULT 'pendente',  -- pendente | validada | rejeitada
    moderado_por    TEXT,
    moderado_em     TIMESTAMPTZ,
    contexto        JSONB,                    -- nível e chuva vigentes no momento informado
    criada_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- auditoria da coleta
CREATE TABLE log_coleta (
    id              BIGSERIAL PRIMARY KEY,
    fonte_id        INTEGER NOT NULL REFERENCES fonte(id),
    executado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duracao_ms      INTEGER NOT NULL,
    registros       INTEGER NOT NULL,
    status          TEXT NOT NULL,            -- sucesso | vazio | falha
    mensagem        TEXT
);
```

A tabela `leitura` guarda o payload bruto em `bruto`. Isso custa espaço, mas permite reprocessar quando a normalização mudar, o que acontece quando uma fonte altera o contrato.

---

## 5. Serviço de ingestão

### 5.1 Interface do adaptador

Todo adaptador implementa a mesma interface. É isso que atende o RNF11 e permite trocar fonte sem tocar no núcleo.

```python
# services/ingestor/src/ingestor/adapters/base.py
from abc import ABC, abstractmethod
from datetime import datetime
from common.schemas import LeituraBruta

class Adaptador(ABC):
    codigo: str
    frequencia_s: int

    @abstractmethod
    def coletar(self, inicio: datetime | None = None,
                fim: datetime | None = None) -> list[LeituraBruta]:
        """Busca na fonte e devolve leituras já no formato interno."""

    @abstractmethod
    def verificar_contrato(self) -> bool:
        """Confere se a resposta ainda tem a estrutura esperada.
        Usado pelo teste de contrato e pelo painel de qualidade."""
```

### 5.2 Adaptador do GraphQL da Defesa Civil

Ponto de atenção: o servidor aceita apenas operações registradas. A consulta precisa ser enviada exatamente como o portal envia, o que está documentado em [fontes-de-dados.md](fontes-de-dados.md#31-operação-tags_data-funciona). Uma única chamada traz todas as estações, então não faz sentido iterar por estação.

```python
QUERY_TAGS_DATA = """query Tags_data { tags_data(clients: ["secretaria-de-defesa-civil"]) {
  qualle_meteorologia { codigo name { prefix general local } timestamp
    position { bacia latitude longitude }
    data { rio { rio_nome { value } rio_nivel { value } }
           chuva { acumulado { h001 { value } h003 { value } h006 { value }
                               h012 { value } h024 { value } h048 { value }
                               h072 { value } h168 { value } } } } } } }"""
```

O retorno traz cada valor dentro de um objeto com `value`, `show`, `format` e `unit`, e a normalização precisa descer até `value`.

### 5.3 Adaptador REST, com carga inicial

O REST é a única via com série de 5 em 5 minutos e serve para dois casos: a carga inicial dos cerca de 80 dias disponíveis e o preenchimento de lacunas deixadas por falha do GraphQL.

```python
URL = ("https://api-dcsc.mks-unifique.ddns.net/api/estacoes/dados"
       "?codigo={codigo}&data_inicial={inicio}&data_final={fim}")
# formato de data aceito: 2026-09-18T00:00-0300
```

A carga inicial é um comando único, executado uma vez, que varre dia a dia cada estação configurada. Precisa rodar no primeiro dia de operação, porque a janela é deslizante e o que sai dela não volta.

### 5.4 Agendamento

```python
# services/ingestor/src/ingestor/main.py
scheduler.add_job(coletar_dcsc_graphql, "interval", minutes=5)
scheduler.add_job(coletar_dcsc_rest_gaps, "interval", minutes=30)
scheduler.add_job(coletar_barragens, "interval", minutes=30)
scheduler.add_job(coletar_openmeteo_forecast, "interval", hours=1)
scheduler.add_job(sincronizar_inventario, "cron", hour=3)
```

### 5.5 Validação de plausibilidade

Regras aplicadas antes de gravar, conforme RF07:

| Regra | Ação |
|---|---|
| Nível negativo ou acima de 15 m | Marca como descartada |
| Variação de nível maior que 100 cm em 5 minutos | Marca como suspeita e não dispara alerta |
| Chuva acumulada de 1h maior que 150 mm | Marca como suspeita |
| Carimbo de tempo no futuro | Descarta |
| Leitura idêntica repetida por mais de 6 horas em estação de nível | Marca sensor como possivelmente travado no painel de qualidade |

---

## 6. Serviço de modelo

### 6.1 Montagem das variáveis

A função central produz, para cada instante `t` da série, uma linha com as variáveis descritas na seção 9.2 da especificação. A janela de agregação usa apenas dado passado em relação a `t`, sem exceção, para não vazar futuro.

```python
def montar_features(estacao_alvo: str, pontos_influencia: list[str],
                    inicio: datetime, fim: datetime) -> pd.DataFrame:
    """Devolve DataFrame indexado por tempo, com:
       chuva_{ponto}_{janela}h    para janelas 1, 3, 6, 12, 24, 48, 72, 168
       nivel_{estacao}, taxa_{estacao}, acel_{estacao}
       barragem_nivel, barragem_comportas_abertas
       prev_chuva_{ponto}_{h}h
       interacao_dona_emma_x_jose_boiteux
       interacao_nivel_norte_x_chuva_local
       mes, hora
    """
```

### 6.2 Análise de correlação defasada

Entrega independente do modelo, que atende o RF13 e testa a hipótese da seção 1.2 da especificação.

```python
def correlacao_defasada(chuva: pd.Series, nivel: pd.Series,
                        defasagens_h: range = range(1, 37)) -> pd.DataFrame:
    """Para cada defasagem, correlaciona a chuva acumulada no ponto
    com a variação de nível na cidade. Devolve a defasagem de maior
    correlação, que é o tempo de resposta típico daquele ponto."""
```

O resultado vira um quadro por ponto de influência, com o tempo de resposta típico e a força da relação. Esse quadro entra no artigo da Fase 4.

### 6.3 Treino e validação

```python
HORIZONTES = [1, 3, 6, 12, 24]

def treinar(estacao: str, horizonte: int) -> ResultadoTreino:
    X, y = montar_features(...), alvo_deslocado(horizonte)
    for treino_idx, teste_idx in TimeSeriesSplit(n_splits=5).split(X):
        ...
    # baselines obrigatórios
    rmse_persistencia = avaliar_persistencia(y, horizonte)
    rmse_tendencia = avaliar_extrapolacao_linear(y, horizonte)
    # só publica se ganhar da persistência
    publicar = resultado.rmse < rmse_persistencia
```

Critério de publicação, que implementa a RN07: o modelo só vai ao ar se superar a persistência e se houver pelo menos 60 dias de dados contínuos para as estações envolvidas. Enquanto isso não acontecer, a API devolve previsão indisponível com o motivo, e o painel mostra apenas o observado.

### 6.4 Versionamento do modelo

Cada treino grava uma linha em `modelo` e um artefato `joblib` em volume compartilhado (`/artefatos/{estacao}/{horizonte}/{id}.joblib`). A API carrega apenas modelos com `publicado = true`. Rollback é uma troca de flag no banco.

---

## 7. API

Endpoints previstos. Documentação automática em `/docs`.

| Método | Rota | Descrição | Caso de uso |
|---|---|---|---|
| GET | `/api/estacoes` | Lista estações com papel e limiares vigentes | CDU01 |
| GET | `/api/estacoes/{codigo}/atual` | Última leitura, tendência e faixa de risco | CDU01, CDU10 |
| GET | `/api/estacoes/{codigo}/serie` | Série histórica por período e variável | CDU01 |
| GET | `/api/chuva/acumulada` | Acumulados por ponto de influência | CDU01 |
| GET | `/api/previsao/{codigo}` | Estimativa por horizonte, com incerteza | CDU02, CDU09 |
| POST | `/api/simulacao` | Recebe chuva por ponto e devolve nível estimado | CDU03 |
| GET | `/api/correlacao` | Tempo de resposta típico por ponto de influência | CDU02 |
| POST | `/api/ocorrencias` | Registra ocorrência informada pela população | CDU04 |
| GET | `/api/ocorrencias` | Lista ocorrências validadas, com filtro | CDU05 |
| PATCH | `/api/ocorrencias/{id}` | Modera ocorrência. Exige autenticação | CDU08 |
| POST | `/api/inscricoes` | Cria inscrição de push | CDU06 |
| DELETE | `/api/inscricoes/{id}` | Cancela inscrição | CDU06, RF39 |
| GET | `/api/alertas` | Alertas vigentes e histórico | CDU07 |
| GET | `/api/qualidade` | Cobertura por estação e falhas recentes | CDU14 |
| POST | `/api/admin/limiares` | Atualiza limiar. Exige autenticação | CDU13 |
| GET | `/api/relatorio` | Gera PDF consolidado | CDU15 |

Convenções: toda resposta que expõe dado de fonte externa traz `fonte`, `estacao` e `medido_em`, o que atende o RNF16. Toda resposta de previsão traz `modelo_id`, `treinado_em` e `incerteza_m`.

---

## 8. Front-end PWA

Telas:

| Tela | Conteúdo | Caso de uso |
|---|---|---|
| Painel | Situação agora das duas estações alvo, tendência, chuva por ponto de influência, gráfico do histórico | CDU01 |
| Previsão | Gráfico com observado e estimado, faixa de incerteza, explicação dos pontos que mais pesaram | CDU02 |
| Simulação | Formulário com chuva por ponto, resultado lado a lado com a situação atual | CDU03 |
| Mapa | Ocorrências validadas, filtro por período, botão de registrar | CDU04, CDU05 |
| Registro | Marcação no mapa, data e hora, tipo de impacto, foto opcional | CDU04 |
| Inscrição | Escolha de estação e faixa, permissão de push, cancelamento | CDU06 |
| Administração | Limiares, pontos de influência, moderação, qualidade de dados | CDU08, CDU13, CDU14 |

Requisitos de PWA: `manifest.webmanifest` com ícones e `display: standalone`, service worker com cache do casco da aplicação para abrir mesmo com rede ruim, e banner de instalação. O service worker não deve cachear resposta de dado ao vivo, apenas o casco, para não mostrar nível antigo como se fosse atual.

---

## 9. Notificação push

Fluxo padrão de Web Push com VAPID, sem dependência de serviço pago.

1. Gerar o par de chaves VAPID uma vez e guardar como segredo: `vapid_private_key` e `vapid_public_key`.
2. O front-end registra o service worker e chama `pushManager.subscribe` com a chave pública.
3. O navegador devolve `endpoint`, `p256dh` e `auth`, que o front envia para `POST /api/inscricoes`.
4. Quando o CDU07 gera alerta, a API envia a notificação com `pywebpush`, assinando com a chave privada.
5. Inscrição que retornar 404 ou 410 é desativada, porque significa que o usuário desinstalou ou revogou.

Push exige HTTPS, inclusive no servidor da UDESC. Em desenvolvimento, `localhost` é aceito como origem segura.

---

## 10. Rodando localmente

Pré-requisito único: Docker Desktop instalado e rodando.

```bash
git clone <url-do-repositorio>
cd Projeto_Integrador_2
cp .env.example .env        # no Windows: copy .env.example .env
docker compose up --build
```

Serviços no ar depois disso:

| Endereço | Serviço |
|---|---|
| http://localhost:5173 | Front-end |
| http://localhost:8000/docs | API, documentação OpenAPI |
| localhost:5432 | Banco, usuário e senha no `.env` |

Comandos do dia a dia:

```bash
# aplicar migrações
docker compose exec api alembic upgrade head

# popular estações e limiares iniciais
docker compose exec api python -m api.seed

# carga inicial dos 80 dias disponíveis (roda uma vez, no primeiro dia)
docker compose exec ingestor python -m ingestor.carga_inicial --dias 80

# rodar a análise de correlação
docker compose exec modelo python -m modelo.correlacao --estacao DCSC-00043

# treinar e avaliar
docker compose exec modelo python -m modelo.treino --estacao DCSC-00043 --horizonte 6

# logs de um serviço
docker compose logs -f ingestor
```

`docker-compose.yml` de referência:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s

  api:
    build: ./services/api
    env_file: .env
    depends_on:
      db: { condition: service_healthy }
    volumes:
      - artefatos:/artefatos
    ports: ["8000:8000"]

  ingestor:
    build: ./services/ingestor
    env_file: .env
    depends_on:
      db: { condition: service_healthy }
    restart: unless-stopped

  modelo:
    build: ./services/modelo
    env_file: .env
    depends_on:
      db: { condition: service_healthy }
    volumes:
      - artefatos:/artefatos

  web:
    build: ./web
    env_file: .env
    depends_on: [api]
    ports: ["5173:5173"]

volumes:
  pgdata:
  artefatos:
```

---

## 11. Configuração e segredos

`.env.example`, que vai versionado, sem valor real:

```env
# banco
POSTGRES_DB=pgetulio
POSTGRES_USER=pgetulio
POSTGRES_PASSWORD=troque_esta_senha
DATABASE_URL=postgresql+psycopg://pgetulio:troque_esta_senha@db:5432/pgetulio

# fontes
DCSC_GRAPHQL_URL=https://monitoramento.defesacivil.sc.gov.br/graphql
DCSC_REST_URL=https://api-dcsc.mks-unifique.ddns.net
OPENMETEO_FORECAST_URL=https://api.open-meteo.com/v1/forecast
OPENMETEO_ARCHIVE_URL=https://archive-api.open-meteo.com/v1/archive
ANA_IDENTIFICADOR=
ANA_SENHA=

# push
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:equipe@exemplo.br

# app
API_BASE_URL=http://localhost:8000
ADMIN_USER=admin
ADMIN_PASSWORD_HASH=
```

Regra que não se quebra: `.env` fica no `.gitignore`. Nenhuma credencial vai para o repositório, nem em exemplo, nem em comentário, nem em teste. Isso atende o RNF09.

---

## 12. Testes

| Tipo | O que cobre | Ferramenta |
|---|---|---|
| Unitário | Normalização, classificação por limiar, validação de plausibilidade, cálculo de tendência | pytest |
| Contrato | Cada adaptador contra uma resposta gravada da fonte real | pytest com fixture em JSON |
| Canário de contrato | Job diário que chama a fonte real e compara a estrutura com a esperada, avisando quando mudar | job no ingestor |
| Integração | API contra banco de teste, com dados semeados | pytest e testcontainers |
| Modelo | Verificação de que não há vazamento temporal e de que o baseline é calculado | pytest |
| Ponta a ponta | Fluxo de registrar ocorrência e de receber push | Playwright |

O canário de contrato existe por um motivo concreto: durante o levantamento, a API documentada pelo professor já tinha mudado. Vai mudar de novo.

---

## 13. Publicação

Ambiente alvo: servidor da UDESC, conforme itens 25 e 26 do cronograma.

Passos:

1. Instalar Docker e Docker Compose no servidor.
2. Clonar o repositório e criar o `.env` com os valores de produção.
3. Subir com `docker compose -f docker-compose.yml up -d --build`.
4. Colocar um Nginx na frente, com HTTPS, encaminhando `/api` para o serviço `api` e o restante para o `web`. HTTPS é obrigatório por causa do push.
5. Agendar backup diário com `pg_dump`, guardando fora do servidor. A base coletada é o ativo mais valioso do projeto, porque não é reconstituível.
6. Monitorar o endpoint `/api/qualidade` e o log de coleta.

Ponto de atenção para a avaliação: se o servidor da UDESC não estiver disponível a tempo, o mesmo `docker compose` sobe em qualquer máquina com Docker, o que reduz o risco RI07.

---

## 14. Roteiro de implementação

Sequência sugerida, pensada para que a coleta comece antes de qualquer tela existir.

| Etapa | Entrega | Por que nesta ordem |
|---|---|---|
| 1 | Banco, migrações e pacote `common` | Base de tudo |
| 2 | `ingestor` com adaptador do GraphQL, agendador e log | Começa a coletar imediatamente, cada dia conta |
| 3 | Carga inicial dos 80 dias via REST | Recupera a única janela histórica que ainda existe |
| 4 | Adaptadores de barragem e de previsão | Completa o conjunto de variáveis |
| 5 | API com estações, série e classificação de risco | Permite montar a primeira tela |
| 6 | Painel no front, com instalação PWA | Primeira entrega visível |
| 7 | Análise de correlação defasada | Primeiro resultado analítico, independente do modelo |
| 8 | Registro e mapa de ocorrências, com moderação | Começa a construir o dado de impacto, que leva tempo para acumular |
| 9 | Treino, validação e publicação de modelo | Depende de dado acumulado nas etapas anteriores |
| 10 | Previsão e simulação no front | Fecha o núcleo do sistema |
| 11 | Alerta e push | Depende de tudo acima estar estável |
| 12 | Relatório, painel de qualidade e publicação no servidor | Fechamento |

As etapas 2 e 3 são as mais urgentes e não dependem de nenhuma decisão pendente. Podem começar antes mesmo da aprovação da especificação.
