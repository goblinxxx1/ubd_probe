#!/bin/sh
set -e

INTERVAL="${CRAWL_INTERVAL_SECONDS:-0}"
if [ "$INTERVAL" -gt 0 ] 2>/dev/null; then
  echo "[crawler] adaptive scheduler loop (CRAWL_INTERVAL_SECONDS=$INTERVAL enables loop mode)"
  exec python -m crawler loop
else
  echo "[crawler] single one-shot pass"
  exec python -m crawler run
fi
