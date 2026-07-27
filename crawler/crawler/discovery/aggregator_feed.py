"""Aggregator-as-domain-feed: a persistent store of business hosts harvested from
blocklisted aggregator directories, plus a rotating feed that re-surfaces them as
website candidates. Same persist+re-feed pattern as osm_feed / brand_feed."""

import copy
import json
import logging
import os

from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "hosts": [], "cursor": 0}


class AggregatorDomainStore:
    """Persistent ordered host list + rotation cursor. Accumulates continuously (no
    freshness gate). Atomic writes; a corrupt/missing file starts clean."""

    def __init__(self, path, data=None):
        self._path = path
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY))

    @classmethod
    def load(cls, path) -> "AggregatorDomainStore":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("aggregator store must be a JSON object")
            for k, default in _EMPTY.items():
                data.setdefault(k, copy.deepcopy(default))
        except (OSError, ValueError) as exc:
            log.warning("aggregator store load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data)

    def domains(self) -> list[str]:
        return list(self._data.get("hosts", []))

    def cursor(self) -> int:
        return int(self._data.get("cursor", 0))

    def set_cursor(self, value: int) -> None:
        self._data["cursor"] = int(value)
        self._save()

    def add(self, hosts, cap: int) -> None:
        cur = list(self._data.get("hosts", []))
        seen = set(cur)
        for h in sorted(hosts):
            if h and h not in seen:
                cur.append(h)
                seen.add(h)
        if len(cur) > cap:
            cur = cur[len(cur) - cap:]      # keep newest cap, drop oldest from the front
        self._data["hosts"] = cur
        self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)


class AggregatorDomainFeed:
    """Rotating window of website SourceCandidates from the store."""

    def __init__(self, store, per_pass=20):
        self._store = store
        self._per_pass = per_pass

    def candidates(self, known) -> list[SourceCandidate]:
        hosts = self._store.domains()
        size = len(hosts)
        if size == 0:
            return []
        n = max(1, min(int(self._per_pass), size))
        cursor = self._store.cursor()
        if cursor < 0 or cursor >= size:
            cursor = 0
        window = [hosts[(cursor + i) % size] for i in range(n)]
        self._store.set_cursor((cursor + n) % size)
        out: list[SourceCandidate] = []
        for host in window:
            url = f"https://{host}"
            if normalize_ref("website", url) in known:
                continue
            out.append(SourceCandidate(
                name=host, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"aggregator-feed:{host}"))
        return out
