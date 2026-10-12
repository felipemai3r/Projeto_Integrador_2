# Desenvolvimento

Código do sistema, separado por camada para facilitar a orientação e a revisão das mudanças.

| Pasta | Conteúdo | Situação |
|---|---|---|
| `backend/db` | Migrações Alembic (esquema do banco) | Esquema inicial pronto |
| `backend/services/common` | Pacote compartilhado: configuração, modelos, contratos, seed | Pronto |
| `backend/services/ingestor` | Coleta das fontes, plausibilidade, gravação, cargas históricas, canário de contrato | GraphQL, REST, barragens e Open-Meteo prontos |
| `backend/services/api` | API FastAPI | Próxima etapa |
| `backend/services/modelo` | Correlação defasada e previsão | Sprint 2 |
| `frontend` | PWA em React, com o design Farol | Próxima etapa |

## Rodando

Pré-requisito: Docker Desktop.

```bash
cd desenvolvimento
cp .env.example .env
docker compose up --build        # sobe db, aplica migrações e seed, inicia a coleta

# carga inicial do histórico disponível na API REST (uma vez; pode repetir sem duplicar)
docker compose exec ingestor python -m ingestor.carga_inicial --dias 82

# histórico longo de chuva (ERA5), desde o evento de dezembro de 2020
docker compose exec ingestor python -m ingestor.carga_era5 --inicio 2020-11-01
```

## Testes e lint (fora do Docker)

O ambiente virtual **não pode ficar dentro do iCloud Drive** (ver [ADR 0001](../docs/adr/0001-achados-da-coleta-inicial.md)).

```bash
python3 -m venv ~/.venvs/pgetulio
~/.venvs/pgetulio/bin/pip install -e "backend/services/common[dev]" -e "backend/services/ingestor[dev]"
docker compose up -d db
~/.venvs/pgetulio/bin/pytest backend/services
~/.venvs/pgetulio/bin/ruff check backend && ~/.venvs/pgetulio/bin/ruff format --check backend
```

Os testes criam o banco `pgetulio_test` do zero a partir das migrações.
