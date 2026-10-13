#!/usr/bin/env bash
# Backup manual (ou por cron) do banco, direto do host, e copia opcional para fora do servidor.
# Uso:  scripts/backup.sh [pasta_destino]
#       DESTINO_REMOTO=usuario@host:/caminho scripts/backup.sh   (copia por rsync/ssh)
set -euo pipefail
cd "$(dirname "$0")/.."
destino="${1:-./backups}"
mkdir -p "$destino"
arq="$destino/pgetulio-$(date -u +%Y%m%d-%H%M).sql.gz"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" --no-owner "$POSTGRES_DB"' | gzip -9 > "$arq"
echo "backup gravado: $arq ($(du -h "$arq" | cut -f1))"
if [ -n "${DESTINO_REMOTO:-}" ]; then
  rsync -a "$arq" "$DESTINO_REMOTO/" && echo "copiado para $DESTINO_REMOTO"
fi
find "$destino" -name 'pgetulio-*.sql.gz' -mtime +30 -delete
