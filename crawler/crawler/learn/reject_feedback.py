"""Reject feedback: moderator-rejected crawler offers → soft down-rank in DomainRegistry.
Mirrors SnowballIngestor (approved-offers), with a JSON `since` cursor."""

import json
import os


class RejectionIngestor:
    def __init__(self, api, registry, state_path: str):
        self._api = api
        self._reg = registry
        self._state_path = state_path

    def _since(self):
        try:
            return json.load(open(self._state_path, encoding="utf-8")).get("since")
        except (OSError, ValueError):
            return None

    def _save_since(self, since):
        os.makedirs(os.path.dirname(self._state_path) or ".", exist_ok=True)
        json.dump({"since": since}, open(self._state_path, "w", encoding="utf-8"))

    def ingest(self) -> int:
        rows = self._api.list_rejected_offers(self._since()) or []
        counts: dict[str, int] = {}
        newest = None
        n = 0
        for row in rows:
            host = (row.get("host") or "").strip()
            if host:
                counts[host] = counts.get(host, 0) + 1
            ts = row.get("rejected_at")
            if ts and (newest is None or ts > newest):
                newest = ts
            n += 1
        for host, cnt in counts.items():
            self._reg.record_rejections(host, cnt)
        if newest:
            self._save_since(newest)
        return n
