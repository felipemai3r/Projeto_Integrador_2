# Desenvolvimento

Código do sistema, separado por camada para facilitar a orientação e a revisão das mudanças.

| Pasta | Conteúdo | Situação |
|---|---|---|
| `backend/db` | Migrações Alembic (esquema do banco) | Esquema inicial pronto |
| `backend/services/common` | Pacote compartilhado: configuração, modelos, contratos, seed | Pronto |
| `backend/services/ingestor` | Coleta das fontes, plausibilidade, gravação, cargas históricas, canário de contrato | GraphQL, REST, barragens e Open-Meteo prontos |
| `backend/services/api` | API FastAPI: leitura, alertas, correlação, ocorrências com moderação, login | Pronta (porta 8000, docs em `/docs`) |
| `backend/services/modelo` | Correlação defasada (RF13); depois treino e previsão | Correlação pronta ([ADR 0003](../docs/adr/0003-correlacao-defasada-primeiros-resultados.md)) |
| `frontend` | PWA em React, com o design Farol ([detalhes](frontend/README.md)) | Painel, histórico, mapa, registro de alagamento, moderação e Como funciona |

## Rodando

Pré-requisito: Docker Desktop.

```bash
cd desenvolvimento
cp .env.example .env
docker compose up --build        # sobe db, aplica migrações e seed, inicia a coleta

# carga inicial do histórico disponível na API REST (uma vez; pode repetir sem duplicar)
docker compose exec ingestor python -m ingestor.carga_inicial --dias 82

# análise de correlação defasada (grava o resultado e imprime a tabela)
docker compose run --rm modelo python -m modelo.correlacao --estacao DCSC-00043

# histórico longo de chuva (ERA5), desde o evento de dezembro de 2020
docker compose exec ingestor python -m ingestor.carga_era5 --inicio 2020-11-01
```

## Moderação: criar usuário

O cidadão não tem conta. Quem modera (Defesa Civil, equipe) entra em `/moderacao` com e-mail e senha. Crie o usuário:

```bash
docker compose exec api python -m api.criar_usuario --email fulano@exemplo.br --nome "Fulano" --papel moderador
# a senha é pedida no terminal (mínimo 10 caracteres). Papéis: admin, moderador
```

## Avisos por push

Gere o par de chaves VAPID uma vez e guarde no `.env` (nunca no Git):

```bash
docker compose run --rm api python -m api.gerar_vapid
```

O push só funciona no app **publicado/instalado** (service worker). Para testar localmente: `cd frontend && npm run build && npm run preview` e abra `http://localhost:4173/avisos`. No iPhone, só depois de adicionar o app à tela inicial. O servidor só aceita inscrições de serviços de push de navegadores conhecidos (proteção contra SSRF).

O `JWT_SECRET` do `.env` é obrigatório (veja `.env.example`). Fotos de ocorrência ficam no volume `fotos`, sem metadados (EXIF removido).

## Testes e lint (fora do Docker)

O ambiente virtual **não pode ficar dentro do iCloud Drive** (ver [ADR 0001](../docs/adr/0001-achados-da-coleta-inicial.md)).

```bash
python3 -m venv ~/.venvs/pgetulio
~/.venvs/pgetulio/bin/pip install -e "backend/services/common[dev]" -e "backend/services/ingestor[dev]" -e "backend/services/api[dev]" -e "backend/services/modelo[dev]"
docker compose up -d db
~/.venvs/pgetulio/bin/pytest backend/services
~/.venvs/pgetulio/bin/ruff check backend && ~/.venvs/pgetulio/bin/ruff format --check backend
```

Os testes criam o banco `pgetulio_test` do zero a partir das migrações.
