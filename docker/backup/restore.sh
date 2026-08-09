#!/bin/sh
# Restore the `ubd` database from a db-backup file. Run on the HOST, from the repo root:
#   sh docker/backup/restore.sh backups/ubd_YYYYmmdd_HHMMSS.sql
# The dump carries `CREATE DATABASE ubd`, so schema + data are fully replaced.
set -eu

FILE="${1:?usage: sh docker/backup/restore.sh <backups/ubd_YYYYmmdd_HHMMSS.sql>}"
CONTAINER="${DB_CONTAINER:-ubd_probe-db-1}"
[ -f "$FILE" ] || { echo "no such file: $FILE" >&2; exit 1; }

# Password: prefer the environment, else read MYSQL_ROOT_PASSWORD from ./.env
if [ -z "${MYSQL_ROOT_PASSWORD:-}" ] && [ -f .env ]; then
  MYSQL_ROOT_PASSWORD=$(sed -n 's/^MYSQL_ROOT_PASSWORD=//p' .env | head -n1)
fi
: "${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD, or run from the repo root where .env lives}"

echo "Restoring '$FILE' into container '$CONTAINER' (database ubd will be replaced)..."
docker exec -i -e MYSQL_PWD="$MYSQL_ROOT_PASSWORD" "$CONTAINER" mysql -uroot < "$FILE"
echo "Done. ubd restored from $FILE."
