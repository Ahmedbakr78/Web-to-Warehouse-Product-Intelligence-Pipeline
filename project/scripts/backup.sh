#!/usr/bin/env bash
# Warehouse backup: pg_dump + mysqldump + sqlite copy into one timestamped directory.
# Usage: ./scripts/backup.sh [output-dir]   (default: ./backups/<timestamp>)
# Restore is intentionally manual — see docs/13_deployment.md.
set -euo pipefail

DEST="${1:-./backups/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$DEST"

echo "--> $DEST"

if command -v pg_dump >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
  # pg_dump understands libpq URLs poorly; translate the SQLAlchemy URL.
  pg_dump "${DATABASE_URL/postgresql+psycopg2/postgresql}" >"$DEST/postgres.sql" 2>"$DEST/postgres.err" \
    && echo "postgres ok" || echo "postgres skipped (see postgres.err)"
else
  echo "postgres skipped (no pg_dump or DATABASE_URL)"
fi

if command -v mysqldump >/dev/null 2>&1 && [ -n "${MYSQL_URL:-}" ]; then
  mysqldump --result-file="$DEST/mysql.sql" --skip-ssl "${MYSQL_URL}" 2>"$DEST/mysql.err" \
    && echo "mysql ok" || echo "mysql skipped (see mysql.err)"
else
  echo "mysql skipped (no mysqldump or MYSQL_URL)"
fi

shopt -s nullglob
SQLITE_FILES=(./var/*.sqlite3 ./*.sqlite3)
if [ "${#SQLITE_FILES[@]}" -gt 0 ]; then
  for db in "${SQLITE_FILES[@]}"; do
    cp "$db" "$DEST/$(basename "$db")"
  done
  echo "sqlite ok (${#SQLITE_FILES[@]} file(s))"
else
  echo "sqlite skipped (no local database files)"
fi

ls -la "$DEST"
echo "backup complete: $DEST"
