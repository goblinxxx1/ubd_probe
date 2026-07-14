#!/bin/sh
set -e

echo "[entrypoint] waiting for DB + running migrations..."
until alembic upgrade head; do
  echo "[entrypoint] alembic failed (db not ready?), retrying in 2s..."
  sleep 2
done

echo "[entrypoint] seeding baseline data..."
python -m app.seed

echo "[entrypoint] starting uvicorn on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
