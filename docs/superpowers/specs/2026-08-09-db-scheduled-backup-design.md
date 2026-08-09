# Scheduled DB backup — design

**Date:** 2026-08-09
**Status:** approved

## Goal

Automatically back up the `ubd` MySQL database to a **host** file every 48 h, with
retention and a documented one-command restore. Motivation: this session recovered
from an AI (Gordon) wiping the DB volume with no usable backup — the safety net must
live **outside** any Docker volume so a volume wipe cannot take it too.

## Design

A dedicated **`db-backup` compose sidecar** (`image: mysql:8.0`, reuses `mysqldump`,
**no profile** → starts with the default stack, always protecting). Script
`docker/backup/backup.sh`:

- One backup **immediately on start**, then every `BACKUP_INTERVAL_SECONDS` (default
  `172800` = 48 h): `mysqldump -h db -uroot --single-transaction --routines --triggers
  --databases ubd` → `/backups/ubd_<UTC-timestamp>.sql`. Password via `MYSQL_PWD`
  (no CLI exposure / no warning). Writes to `*.part` then atomically `mv`s into place.
- **Retention:** keep the newest **7** dumps (~2 weeks at 48 h); prune older.
- **Manual one-off:** `docker compose exec db-backup sh /usr/local/bin/backup.sh once`.

**Storage:** host bind-mount `./backups:/backups` — on the host filesystem, so backups
survive `docker compose down -v` and any DB-volume wipe. `backups/` is gitignored.

**Restore:** `docker/backup/restore.sh <file>` (run on the host):
`docker exec -i -e MYSQL_PWD=… ubd_probe-db-1 mysql -uroot < <file>`. The dump carries
`CREATE DATABASE ubd`, so schema + data are fully replaced. Documented in `README-docker.md`.

**Format:** plain `.sql` (DB is tiny; no gzip dependency; trivial restore).

## Files

- Create: `docker/backup/backup.sh`, `docker/backup/restore.sh`
- Modify: `docker-compose.yml` (add `db-backup` service), `.gitignore` (add `backups/`),
  `.env.example` (add `BACKUP_INTERVAL_SECONDS`), `README-docker.md` (Backups section)

## Verification

1. `docker compose up -d db-backup` → within seconds a `backups/ubd_*.sql` file appears.
2. Restore round-trip into the scratch `ubd_restore` database proves the dump is valid
   and loadable, without touching live `ubd`.

## Out of scope

Off-site/remote replication, encryption, gzip compression, point-in-time (binlog) recovery.
