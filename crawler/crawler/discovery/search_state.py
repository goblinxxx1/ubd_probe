import copy
import json
import logging
import os
import time

from crawler.models import SourceCandidate

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "approved_cursor": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}, "phrase_pages": {},
          "phrase_stats": {}, "host_freq": {}}


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

    # --- query-grid rotation cursor (separate from backend `cursor`) ---
    @property
    def grid_cursor(self) -> int:
        return int(self._data.get("grid_cursor", 0))

    def set_grid_cursor(self, value: int) -> None:
        self._data["grid_cursor"] = int(value)
        self._save()

    # --- site-query rotation cursor (separate from grid/backend cursors) ---
    @property
    def site_cursor(self) -> int:
        return int(self._data.get("site_cursor", 0))

    def set_site_cursor(self, value: int) -> None:
        self._data["site_cursor"] = int(value)
        self._save()

    # --- approved-partner rotation cursor (site: lever; independent of term phase) ---
    @property
    def approved_cursor(self) -> int:
        return int(self._data.get("approved_cursor", 0))

    def set_approved_cursor(self, value: int) -> None:
        self._data["approved_cursor"] = int(value)
        self._save()

    # --- backend health ---
    def is_healthy(self, backend: str) -> bool:
        b = self._data["backends"].get(backend)
        if not b:
            return True
        return self._clock() >= b.get("cooldown_until", 0.0)

    def record_success(self, backend: str) -> None:
        self._data["backends"][backend] = {
            "fails": 0, "cooldown_until": 0.0,
            "quarantined_until": 0.0, "next_reprobe_at": 0.0}
        self._save()

    def record_block(self, backend: str, base: float, cap: float, jitter: float, rand,
                     *, quarantine_threshold: int = 0, quarantine_seconds: float = 0.0,
                     reprobe_seconds: float = 0.0) -> float:
        b = self._data["backends"].get(backend) or {"fails": 0, "cooldown_until": 0.0}
        fails = int(b.get("fails", 0)) + 1
        delay = min(base * (2 ** (fails - 1)), cap) * (1 + rand() * jitter)
        now = self._clock()
        entry = {"fails": fails, "cooldown_until": now + delay,
                 "quarantined_until": b.get("quarantined_until", 0.0),
                 "next_reprobe_at": b.get("next_reprobe_at", 0.0)}
        # Structurally-dead backend: quarantine it so it stops dragging the pool to all-cool.
        # A failing re-probe re-enters here (fails already >= threshold) → quarantine re-extended
        # and next re-probe pushed out. A success (record_success) is the only reset.
        if quarantine_threshold and fails >= quarantine_threshold:
            entry["quarantined_until"] = now + quarantine_seconds
            entry["next_reprobe_at"] = now + reprobe_seconds
        self._data["backends"][backend] = entry
        self._save()
        return delay

    def is_quarantined(self, backend: str) -> bool:
        b = self._data["backends"].get(backend)
        return bool(b) and self._clock() < b.get("quarantined_until", 0.0)

    def reprobe_due(self, backend: str) -> bool:
        """Quarantined AND its single low-frequency trial window has arrived."""
        b = self._data["backends"].get(backend)
        if not b:
            return False
        now = self._clock()
        return now < b.get("quarantined_until", 0.0) and now >= b.get("next_reprobe_at", 0.0)

    def soonest_recovery(self, pool: list[str], floor: float) -> float:
        """Seconds until the earliest backend becomes selectable again, clamped up to `floor`.
        Quarantined-not-due backends contribute their next_reprobe_at; others their cooldown."""
        now = self._clock()
        remaining = []
        for name in pool:
            e = self._data["backends"].get(name)
            if e is None:
                continue
            if now < e.get("quarantined_until", 0.0) and now < e.get("next_reprobe_at", 0.0):
                remaining.append(e.get("next_reprobe_at", 0.0) - now)
            else:
                remaining.append(max(0.0, e.get("cooldown_until", 0.0) - now))
        base = min(remaining) if remaining else floor
        return max(floor, base)

    # --- global backoff ---
    def in_global_backoff(self) -> bool:
        return self._clock() < self._data.get("next_allowed_at", 0.0)

    def seconds_until_allowed(self) -> float:
        return max(0.0, self._data.get("next_allowed_at", 0.0) - self._clock())

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

    # --- per-phrase SERP page cursor + cadence (Track 3) ---
    def current_page(self, phrase: str) -> int:
        """The SERP page to fetch next for `phrase` (1-based). Default 1."""
        e = self._data.get("phrase_pages", {}).get(self._key(phrase))
        return int(e.get("page", 1)) if e else 1

    def record_page_result(self, phrase: str, page: int, new_count: int,
                           page_cap: int) -> None:
        """Advance/stop the per-phrase page cursor from the search-time new-candidate
        count. Productive (new>0) → next page (reset at the cap). Dry (new==0) → probe ONE
        more page; a SECOND consecutive dry confirms nothing and stops (reset to page 1,
        so the due-walk revisits from page 1 only after the freshness TTL)."""
        pages = self._data.setdefault("phrase_pages", {})
        k = self._key(phrase)
        prev_dry = int((pages.get(k) or {}).get("dry", 0))
        if new_count > 0:
            nxt, dry = (page + 1 if page < page_cap else 1), 0
        else:
            dry = prev_dry + 1
            if dry >= 2 or page >= page_cap:       # confirmed empty, or hit the ceiling
                nxt, dry = 1, 0
            else:                                  # first dry → probe one more page
                nxt = page + 1
        pages[k] = {"page": nxt, "dry": dry}
        self._save()

    # --- per-phrase productivity (adaptive scheduling) ---
    def record_yield(self, phrase: str, new_count: int, alpha: float = 0.3) -> None:
        """EWMA урожайності фрази + лічильник спроб + серія «сухих» проходів.
        Продуктивність (new_count) уже known-filtered у SearchPass → це маргінальні
        НОВІ кандидати. Живить effective_ttl (рідше вертатись до сухих фраз)."""
        stats = self._data.setdefault("phrase_stats", {})
        k = self._key(phrase)
        e = stats.get(k) or {"tries": 0, "ewma": 0.0, "dry_streak": 0}
        e["tries"] = int(e.get("tries", 0)) + 1
        prev = float(e.get("ewma", 0.0))
        e["ewma"] = (1.0 - alpha) * prev + alpha * float(new_count)
        e["dry_streak"] = 0 if new_count > 0 else int(e.get("dry_streak", 0)) + 1
        stats[k] = e
        self._save()

    def effective_ttl(self, phrase: str, base_ttl: float, *,
                      cold_tries: int = 3, mult_cap: float = 8.0) -> float:
        """Адаптивний freshness-TTL. Молоду фразу (tries<cold_tries) НІКОЛИ не
        душимо (exploration). Продуктивну (ewma>0) вертаємо на базовій каденції.
        Теплу-але-суху — експоненційно рідше (backoff, capped = reprobe-floor),
        той самий патерн, що quarantine/reprobe для бекендів."""
        e = self._data.get("phrase_stats", {}).get(self._key(phrase))
        if not e or int(e.get("tries", 0)) < cold_tries:
            return base_ttl
        if float(e.get("ewma", 0.0)) > 0.0:
            return base_ttl
        dry = int(e.get("dry_streak", 0))
        mult = min(mult_cap, 2.0 ** max(0, dry - cold_tries + 1))
        return base_ttl * mult

    # --- global capture-recapture frequencies (coverage gauge) ---
    def note_host(self, host: str | None) -> None:
        """Зарахувати ще одне «спостереження» домену (для Chao1). Частота, не факт
        наявності — тому інкремент щоразу, коли пошук виносить цей хост."""
        if not host:
            return
        freq = self._data.setdefault("host_freq", {})
        freq[host] = int(freq.get(host, 0)) + 1
        self._save()

    def coverage_counts(self) -> tuple[int, int, int]:
        """(observed, f1, f2): різних доменів, singletons (=1), doubletons (=2)."""
        freq = self._data.get("host_freq", {})
        observed = len(freq)
        f1 = sum(1 for v in freq.values() if int(v) == 1)
        f2 = sum(1 for v in freq.values() if int(v) == 2)
        return observed, f1, f2

    # --- keyword cache (page-aware; page 1 uses the bare key for back-compat) ---
    def is_fresh(self, keyword: str, ttl_seconds: float, page: int = 1) -> bool:
        """True iff a non-expired cache entry exists for `(keyword, page)`."""
        entry = self._data["cache"].get(self._key(keyword, page))
        if not entry:
            return False
        return self._clock() - entry.get("ts", 0.0) < ttl_seconds

    def cache_get(self, keyword: str, ttl_seconds: float,
                  page: int = 1) -> list[SourceCandidate] | None:
        entry = self._data["cache"].get(self._key(keyword, page))
        if not entry or self._clock() - entry.get("ts", 0.0) >= ttl_seconds:
            return None
        return [SourceCandidate(name=c["name"], type=c["type"], url_or_handle=c["url_or_handle"],
                                discovered_from_source_id=None,
                                discovery_note=f"ddg-cache: {self._key(keyword, page)}")
                for c in entry.get("candidates", [])]

    def cache_put(self, keyword: str, candidates: list[SourceCandidate],
                  page: int = 1) -> None:
        self._data["cache"][self._key(keyword, page)] = {
            "ts": self._clock(),
            "harvested": False,
            "candidates": [{"name": c.name, "type": c.type, "url_or_handle": c.url_or_handle}
                           for c in candidates],
        }
        self._save()

    def mark_harvested(self, keywords: list[str]) -> None:
        cache = self._data["cache"]
        touched = False
        for kw in keywords:
            entry = cache.get(self._key(kw))
            if entry is not None and not entry.get("harvested", True):
                entry["harvested"] = True
                touched = True
        if touched:
            self._save()

    def unharvested(self, ttl_seconds: float) -> list[tuple[str, list["SourceCandidate"]]]:
        now = self._clock()
        rows = []
        for key, entry in self._data["cache"].items():
            if entry.get("harvested", True):          # missing key == legacy == done
                continue
            if now - entry.get("ts", 0.0) >= ttl_seconds:
                continue
            rows.append((entry.get("ts", 0.0), key, entry.get("candidates", [])))
        rows.sort(key=lambda r: r[0])                 # oldest ts first
        out = []
        for _ts, key, raw in rows:
            out.append((key, [SourceCandidate(name=c["name"], type=c["type"],
                                              url_or_handle=c["url_or_handle"],
                                              discovered_from_source_id=None,
                                              discovery_note=f"ddg-cache: {key}",
                                              origin_key=key)
                              for c in raw]))
        return out

    @staticmethod
    def _key(keyword: str, page: int = 1) -> str:
        base = keyword.strip().casefold()
        return base if int(page) <= 1 else f"{base}#p{int(page)}"

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
