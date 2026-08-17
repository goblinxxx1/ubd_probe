"""Escalate a per-host media signal to a persistent no-fetch block: push the host to
the backend blocked_hosts table (approved, system) and add it to the runtime blocklist
so it drops immediately this run. Best-effort: a failed backend call is logged, not raised,
and block() returns False so the caller skips latching and the next crawl retries the block."""

import logging

from crawler.discovery import blocklist

log = logging.getLogger(__name__)


class MediaAutoBlocker:
    def __init__(self, api):
        self._api = api

    def block(self, host, sample_url=None) -> bool:
        if not host:
            return False
        try:
            self._api.auto_block_host(host, sample_url)
        except Exception as exc:  # noqa: BLE001 — block must never sink the run
            log.warning("media auto-block failed for %s: %s", host, exc)
            return False
        blocklist.add_learned(host)
        return True
