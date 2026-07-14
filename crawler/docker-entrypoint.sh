#!/bin/sh
set -e

INTERVAL="${CRAWL_INTERVAL_SECONDS:-0}"
if [ "$INTERVAL" -gt 0 ] 2>/dev/null; then
  echo "[crawler] scheduled loop every ${INTERVAL}s"
  while true; do
    python -m crawler run || echo "[crawler] run failed, continuing"
    sleep "$INTERVAL"
  done
else
  echo "[crawler] single one-shot pass"
  exec python -m crawler run
fi
