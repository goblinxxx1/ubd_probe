"""Persistent language-block: hosts judged non-Ukrainian by the language gate
(homepage content + hreflang) get pinned so the WHOLE host is never crawled again.

Kept on the crawler /data volume (like geo_block/domain_registry) — self-contained,
no backend dependency. On load() and on every add() the set is pushed into
discovery.blocklist so is_blocked_host (used by harvest, walk, feeds, attribution)
respects it everywhere at once. Mirrors GeoBlockStore."""

import json
import logging
import os
import threading

from crawler.discovery import blocklist
from crawler.util.hosts import bare_host

log = logging.getLogger(__name__)


class LangBlockStore:
    def __init__(self, path: str):
        self._path = path
        self._hosts: set[str] = set()
        self._lock = threading.Lock()

    def load(self) -> "LangBlockStore":
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, ValueError, OSError):
            data = []
        self._hosts = {h for h in (bare_host(x) for x in data if x) if h}
        self._push()
        return self

    def hosts(self) -> frozenset[str]:
        return frozenset(self._hosts)

    def add(self, host_or_url: str | None) -> bool:
        """Pin a host (accepts a full URL). Returns True if newly added."""
        h = bare_host(host_or_url)
        if not h:
            return False
        with self._lock:
            if h in self._hosts:
                return False
            self._hosts.add(h)
            self._save()
            self._push()
            return True

    def _push(self) -> None:
        blocklist.reload_lang_blocked(self._hosts)

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sorted(self._hosts), f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError as e:
            log.warning("lang-block save failed: %s", e)
