import copy
import json
import logging
import os
import time

from crawler.models import SourceCandidate

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "cursor": 0, "next_allowed_at": 0.0, "backends": {}, "cache": {}}


class SearchState:
    """Persistent JSON state for anti-throttled search: per-backend cooldown,
    keyword cache, rotation cursor, and global backoff. Mutations write atomically."""

    def __init__(self, path: str, data: dict | None = None, clock=time.time):
        self._path = path
        self._clock = clock
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY))
        self._degraded = False

    @classmethod
    def load(cls, path: str, clock=time.time) -> "SearchState":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("search state must be a JSON object")
            for k, default in _EMPTY.items():
                data.setdefault(k, copy.deepcopy(default))
        except (OSError, ValueError) as exc:
            log.warning("search state load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data, clock=clock)

    # --- rotation cursor ---
    @property
    def cursor(self) -> int:
        return int(self._data["cursor"])

    def set_cursor(self, value: int) -> None:
        self._data["cursor"] = int(value)
        self._save()

    # --- backend health ---
    def is_healthy(self, backend: str) -> bool:
        b = self._data["backends"].get(backend)
        if not b:
            return True
        return self._clock() >= b.get("cooldown_until", 0.0)

    def record_success(self, backend: str) -> None:
        self._data["backends"][backend] = {"fails": 0, "cooldown_until": 0.0}
        self._save()

    def record_block(self, backend: str, base: float, cap: float, jitter: float, rand) -> float:
        b = self._data["backends"].get(backend) or {"fails": 0, "cooldown_until": 0.0}
        fails = int(b.get("fails", 0)) + 1
        delay = min(base * (2 ** (fails - 1)), cap) * (1 + rand() * jitter)
        self._data["backends"][backend] = {"fails": fails, "cooldown_until": self._clock() + delay}
        self._save()
        return delay

    # --- global backoff ---
    def in_global_backoff(self) -> bool:
        return self._clock() < self._data.get("next_allowed_at", 0.0)

    def set_global_backoff(self, seconds: float) -> None:
        self._data["next_allowed_at"] = self._clock() + seconds
        self._save()

    # --- transient degradation signal (in-memory only; never persisted) ---
    def mark_degraded(self) -> None:
        """Flag the most recent provider call as degraded (all attempted backends
        failed / no search happened) so a wrapping SearchCache won't cache the empty."""
        self._degraded = True

    def clear_degraded(self) -> None:
        self._degraded = False

    def degraded_last_call(self) -> bool:
        return self._degraded

    # --- keyword cache ---
    def cache_get(self, keyword: str, ttl_seconds: float) -> list[SourceCandidate] | None:
        entry = self._data["cache"].get(self._key(keyword))
        if not entry or self._clock() - entry.get("ts", 0.0) >= ttl_seconds:
            return None
        return [SourceCandidate(name=c["name"], type=c["type"], url_or_handle=c["url_or_handle"],
                                discovered_from_source_id=None,
                                discovery_note=f"ddg-cache: {self._key(keyword)}")
                for c in entry.get("candidates", [])]

    def cache_put(self, keyword: str, candidates: list[SourceCandidate]) -> None:
        self._data["cache"][self._key(keyword)] = {
            "ts": self._clock(),
            "candidates": [{"name": c.name, "type": c.type, "url_or_handle": c.url_or_handle}
                           for c in candidates],
        }
        self._save()

    @staticmethod
    def _key(keyword: str) -> str:
        return keyword.strip().casefold()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
