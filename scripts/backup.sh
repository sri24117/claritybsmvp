#!/bin/sh
set -eu
mkdir -p backups
chmod 700 backups
BACKUP_NAME="claritybs-$(date -u +%Y%m%dT%H%M%SZ).enc"
docker compose run --rm --no-deps -v "$(pwd)/backups:/backups" --user "$(id -u):$(id -g)" api python -m app.cli backup --file "/backups/$BACKUP_NAME"
find backups -maxdepth 1 -type f -name 'claritybs-*.enc' -mtime +6 -delete
