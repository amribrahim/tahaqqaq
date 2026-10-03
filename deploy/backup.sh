#!/usr/bin/env bash
# Nightly logical backup of the production database (pg_dump custom format), keeping the newest 7.
# Installed on the server as a cron job:  17 2 * * *  /opt/tahaqqaq/deploy/backup.sh >> /opt/tahaqqaq/backups/backup.log 2>&1
# Restore:  docker compose -f docker-compose.prod.yml exec -T db pg_restore -U tahqaq -d tahqaq --clean --if-exists < backups/<file>.dump
# The corpus itself can also be rebuilt from the public sources with the ingest scripts; the dump saves that time
# and keeps the growing الدرر cache (source_cache).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
f="backups/tahqaq-$(date -u +%Y%m%d-%H%M).dump"
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U tahqaq -d tahqaq -Fc > "$f.tmp"
mv "$f.tmp" "$f"
ls -1t backups/tahqaq-*.dump | tail -n +8 | xargs -r rm --
echo "$(date -u +%FT%TZ) backup $f $(du -h "$f" | cut -f1)"
