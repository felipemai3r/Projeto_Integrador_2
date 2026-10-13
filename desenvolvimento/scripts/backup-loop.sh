#!/bin/sh
# Roda dentro do servico "backup": um pg_dump compactado por dia, mantendo 14 dias.
set -eu
while true; do
  arq="/backups/pgetulio-$(date -u +%Y%m%d-%H%M).sql.gz"
  if pg_dump --no-owner | gzip -9 > "$arq.tmp"; then
    mv "$arq.tmp" "$arq"
    echo "backup ok: $arq ($(du -h "$arq" | cut -f1))"
  else
    rm -f "$arq.tmp"
    echo "BACKUP FALHOU" >&2
  fi
  find /backups -name 'pgetulio-*.sql.gz' -mtime +14 -delete
  sleep 86400
done
