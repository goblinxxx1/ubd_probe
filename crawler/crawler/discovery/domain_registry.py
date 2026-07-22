"""Persistent crawler-side domain rating: exp-decay score per bare host, fed by every
actively fetched website domain. Governs the DomainFeed and active budget ordering.
Live moderation gate is untouched — this only decides who/what order we actively fetch."""

import copy
import json
import logging
import os
import time

from crawler.discovery.brand_feed import _host  # idempotent bare-host (bare or full URL)

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "domains": {}}


class DomainRegistry:
    def __init__(self, path, data=None, clock=time.time, *,
                 decay=0.9, offer_weight=1.0, error_weight=0.5, promote_min_score=0.5):
        self._path = path
        self._clock = clock
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY))
        self._decay = decay
        self._offer_w = offer_weight
        self._error_w = error_weight
        self._promote = promote_min_score

    @classmethod
    def load(cls, path, clock=time.time, **score_kw):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("domain registry must be a JSON object")
            for k, default in _EMPTY.items():
                data.setdefault(k, copy.deepcopy(default))
        except (OSError, ValueError) as exc:
            log.warning("domain registry load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data, clock=clock, **score_kw)

    def record(self, host, offers, errors):
        host = _host(host)
        if not host:
            return
        now = self._clock()
        e = self._data["domains"].get(host)
        if e is None:
            e = {"score": 0.0, "offers": 0, "errors": 0, "passes": 0,
                 "empty_passes": 0, "first_seen": now, "last_seen": now, "last_offer": 0.0}
            self._data["domains"][host] = e
        e["score"] = max(0.0, e["score"] * self._decay
                         + offers * self._offer_w - errors * self._error_w)
        e["offers"] += int(offers)
        e["errors"] += int(errors)
        e["passes"] += 1
        if offers == 0:
            e["empty_passes"] += 1
        else:
            e["last_offer"] = now
        e["last_seen"] = now

    def score(self, host):
        e = self._data["domains"].get(_host(host))
        return float(e["score"]) if e else 0.0

    def top(self, n, known_hosts):
        rows = [(h, e["score"]) for h, e in self._data["domains"].items()
                if e["score"] >= self._promote and h not in known_hosts]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return [h for h, _ in rows[:max(0, int(n))]]

    def prune(self, evict_min_score, evict_ttl_seconds):
        now = self._clock()
        dead = [h for h, e in self._data["domains"].items()
                if e["score"] < evict_min_score
                and now - e["last_seen"] >= evict_ttl_seconds]
        for h in dead:
            del self._data["domains"][h]
        return len(dead)

    def save(self):
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
