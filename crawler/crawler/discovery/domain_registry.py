"""Persistent crawler-side domain rating: exp-decay score per bare host, fed by every
actively fetched website domain. Governs the DomainFeed and active budget ordering.
Live moderation gate is untouched — this only decides who/what order we actively fetch."""

import copy
import json
import logging
import os
import threading
import time

from crawler.discovery.brand_feed import _host  # idempotent bare-host (bare or full URL)

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "domains": {}}


class DomainRegistry:
    def __init__(self, path, data=None, clock=time.time, *,
                 decay=0.9, offer_weight=1.0, error_weight=0.5, promote_min_score=0.5,
                 reject_weight=1.0, empty_skip=5):
        self._path = path
        self._clock = clock
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY))
        self._decay = decay
        self._offer_w = offer_weight
        self._error_w = error_weight
        self._promote = promote_min_score
        self._reject_w = reject_weight
        self._empty_skip = int(empty_skip)
        # захищає мутатори від втрати оновлень при паралельних викликах з різних потоків
        self._lock = threading.Lock()

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

    def record(self, host, offers, errors, structural_provider=False):
        host = _host(host)
        if not host:
            return
        with self._lock:
            now = self._clock()
            e = self._data["domains"].get(host)
            if e is None:
                e = {"score": 0.0, "offers": 0, "errors": 0, "rejects": 0, "passes": 0,
                     "empty_passes": 0, "skip_left": 0, "first_seen": now, "last_seen": now,
                     "last_offer": 0.0, "media_streak": 0, "provider_ever": False,
                     "media_blocked": False}
                self._data["domains"][host] = e
            e["score"] = max(0.0, e["score"] * self._decay
                             + offers * self._offer_w - errors * self._error_w)
            e["offers"] += int(offers)
            e["errors"] += int(errors)
            e["passes"] += 1
            if offers == 0:
                e["empty_passes"] += 1
                e["skip_left"] = self._empty_skip   # empty pass → skip the host's next N crawls
            else:
                e["last_offer"] = now
                e["skip_left"] = 0                   # productive again → resume normal cadence
            # media-streak: a host that keeps producing offers but never declares itself a
            # business (no Offer/LocalBusiness schema) behaves like media/aggregator.
            if structural_provider:
                e["provider_ever"] = True
                e["media_streak"] = 0
            elif offers > 0:
                e["media_streak"] = e.get("media_streak", 0) + 1
            e["last_seen"] = now

    def media_block_due(self, host, k) -> bool:
        """Pure predicate: True whenever the host has produced offers in >= k crawls
        without ever showing structural provider-evidence and has not already been
        blocked. Does NOT mutate — the caller latches via mark_media_blocked() only
        after the block is confirmed, so a failed block is retried next crawl."""
        e = self._data["domains"].get(_host(host))
        if not e or e.get("provider_ever") or e.get("media_blocked"):
            return False
        return e.get("media_streak", 0) >= int(k)

    def mark_media_blocked(self, host) -> None:
        """Latch a host as blocked so media_block_due stops firing for it. Call ONLY
        after MediaAutoBlocker.block() confirms success. No-op for an unknown host."""
        with self._lock:
            e = self._data["domains"].get(_host(host))
            if e is not None:
                e["media_blocked"] = True

    def take_skip(self, host) -> bool:
        """Empty-pass cooldown gate. If the host still owes skipped crawls, consume one and
        return True (caller must skip this crawl); otherwise return False (crawl proceeds).
        Unknown host → False. Mutates state, so the caller's pass must save() the registry."""
        with self._lock:
            e = self._data["domains"].get(_host(host))
            if e and e.get("skip_left", 0) > 0:
                e["skip_left"] -= 1
                return True
            return False

    def record_rejections(self, host, n):
        """Soft down-rank an EXISTING domain by n rejections (score -= n*reject_weight,
        clamped >=0). No-op for an unknown/empty host — nothing to re-feed. Does not touch
        offers/errors/passes/last_seen (a rejection is not a crawl pass)."""
        host = _host(host)
        with self._lock:
            e = self._data["domains"].get(host)
            if not host or e is None or n <= 0:
                return
            e["score"] = max(0.0, e["score"] - n * self._reject_w)
            e["rejects"] = e.get("rejects", 0) + int(n)

    def score(self, host):
        e = self._data["domains"].get(_host(host))
        return float(e["score"]) if e else 0.0

    def seen_within(self, host, seconds) -> bool:
        e = self._data["domains"].get(_host(host))
        return e is not None and (self._clock() - e["last_seen"]) < seconds

    def top(self, n, known_hosts, cooldown_seconds=0):
        now = self._clock()
        rows = [(h, e["score"]) for h, e in self._data["domains"].items()
                if e["score"] >= self._promote and h not in known_hosts
                and not (cooldown_seconds and now - e["last_seen"] < cooldown_seconds)]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return [h for h, _ in rows[:max(0, int(n))]]

    def prune(self, evict_min_score, evict_ttl_seconds):
        with self._lock:
            now = self._clock()
            dead = [h for h, e in self._data["domains"].items()
                    if e["score"] < evict_min_score
                    and now - e["last_seen"] >= evict_ttl_seconds]
            for h in dead:
                del self._data["domains"][h]
            return len(dead)

    def save(self):
        # знімок під локом, запис файлу — поза локом (щоб не тримати лок під час I/O)
        with self._lock:
            snapshot = copy.deepcopy(self._data)
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        os.replace(tmp, self._path)
