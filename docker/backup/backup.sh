#!/bin/sh
# Scheduled `ubd` database backup. Runs as the `db-backup` compose sidecar:
#   - one backup immediately on start, then every BACKUP_INTERVAL_SECONDS (default 48h)
#   - keeps the newest $KEEP dumps under /backups, a HOST bind-mount, so the backups
#     survive `docker compose down -v` and any DB-volume wipe.
# Manual one-off:  docker compose exec db-backup sh /usr/local/bin/backup.sh once
set -eu

BACKUP_DIR="/backups"
DB="ubd"
KEEP=7
HOST="${DB_HOST:-db}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-172800}"   # 48h
export MYSQL_PWD="${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD required}"

do_backup() {
  mkdir -p "$BACKUP_DIR"
  ts=$(date -u +%Y%m%d_%H%M%S)
  out="$BACKUP_DIR/ubd_${ts}.sql"
  tmp="${out}.part"
  echo "[db-backup] dumping $DB -> $out"
  if mysqldump -h "$HOST" -uroot --single-transaction --routines --triggers \
       --databases "$DB" > "$tmp"; then
    mv "$tmp" "$out"
    echo "[db-backup] wrote $out ($(wc -c < "$out") bytes)"
  else
    echo "[db-backup] ERROR: mysqldump failed; previous backups kept" >&2
    rm -f "$tmp"
    return 1
  fi
  # retention: delete all but the newest $KEEP
  ls -1t "$BACKUP_DIR"/ubd_*.sql 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    echo "[db-backup] pruning $old"
    rm -f "$old"
  done
  return 0
}

if [ "${1:-}" = "once" ]; then
  do_backup
  exit $?
fi

echo "[db-backup] scheduled loop: every ${INTERVAL}s, keep last ${KEEP}, dir=${BACKUP_DIR}"
while true; do
  do_backup || echo "[db-backup] backup attempt failed, will retry next cycle" >&2
  sleep "$INTERVAL"
done
