#!/usr/bin/env bash
# Restaura um backup em um banco NOVO e confere as contagens. Nunca sobrescreve o banco em uso.
# Uso: scripts/restaurar.sh backups/pgetulio-AAAAMMDD-HHMM.sql.gz [nome_do_banco_de_teste]
set -euo pipefail
cd "$(dirname "$0")/.."
arq="${1:?informe o arquivo de backup}"
banco="${2:-pgetulio_restauracao}"
docker compose exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS $banco' -c 'CREATE DATABASE $banco'"
gunzip -c "$arq" | docker compose exec -T db sh -c "psql -q -U \"\$POSTGRES_USER\" -d $banco"
docker compose exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d $banco -tc \"select 'leituras', count(*) from leitura union all select 'estacoes', count(*) from estacao union all select 'alertas', count(*) from alerta union all select 'ocorrencias', count(*) from ocorrencia\""
echo "restauracao ok no banco '$banco'. Para apagar: docker compose exec db psql -U \$POSTGRES_USER -d postgres -c 'DROP DATABASE $banco'"
