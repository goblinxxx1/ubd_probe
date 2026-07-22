"""Snowball: прийняті модератором (published) офери → корпус як сильний PASS."""

import json
import os

from crawler.models import RawItem


class SnowballIngestor:
    def __init__(self, api, recorder, state_path: str):
        self._api = api
        self._rec = recorder
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
        rows = self._api.list_approved_offers(self._since()) or []
        n = 0
        newest = None
        for row in rows:
            item = RawItem(source_id=0, platform="website", key="snowball",
                           text=row.get("text", ""),
                           url=f"https://{row.get('host', '')}")
            self._rec.record(item, True, snowball=True)
            n += 1
            newest = row.get("approved_at") or newest
        if newest:
            self._save_since(newest)
        return n
