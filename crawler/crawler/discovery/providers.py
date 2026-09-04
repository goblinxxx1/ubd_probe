import logging
import random
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
from ddgs import DDGS
from ddgs.exceptions import RatelimitException, TimeoutException

from crawler.discovery.active import ActiveDiscovery
from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate
from crawler.util.hosts import bare_host

log = logging.getLogger(__name__)


def _normalize_url(url: str) -> str | None:
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query)
                       if not k.lower().startswith("utm_")])
    path = p.path.rstrip("/")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


def _is_empty_result(exc: Exception) -> bool:
    """True when ddgs signalled a genuinely empty (but healthy) backend response rather
    than a throttle/timeout/HTTP failure. ddgs raises ``DDGSException('No results found.')``
    only when every engine answered without error yet the ranked result set was empty
    (ddgs.py: ``err or "No results found."`` with ``err`` falsy). Rate limits and timeouts
    are their own subclasses and carry their own messages, so they never match here."""
    if isinstance(exc, (RatelimitException, TimeoutException)):
        return False
    return str(exc).strip() == "No results found."


_IG_RESERVED = ("/p/", "/reel/", "/reels/", "/explore/", "/stories/")
_FB_RESERVED = ("/share", "/sharer", "/events", "/photo", "/watch")


def classify_candidate(url: str) -> tuple[str, str] | None:
    """Map a search-result URL to (source_type, url_or_handle), or None to skip."""
    norm = _normalize_url(url)
    if not norm:
        return None
    parts = urlsplit(norm)
    host = bare_host(norm)
    path = parts.path or "/"
    if host in ("t.me", "telegram.me"):
        return ("telegram", norm)
    if host == "instagram.com":
        if path == "/" or any(path.startswith(p) for p in _IG_RESERVED):
            return None
        return ("instagram", norm)
    if host in ("facebook.com", "fb.com"):
        if path == "/" or any(path.startswith(p) for p in _FB_RESERVED):
            return None
        return ("facebook", norm)
    return ("website", norm)


class RotatingDdgProvider:
    """Callable (keyword) -> list[SourceCandidate].

    Queries ONE backend per keyword, round-robin across `pool`, skipping backends
    in cooldown. A failing backend is cooled (exponential backoff) and the keyword
    falls through to the next healthy one. When no backend is healthy, sets a global
    backoff and returns []. Any non-success outcome flags the shared state degraded so a
    wrapping SearchCache does not cache the empty. Best-effort: never raises for a single keyword.
    """

    def __init__(self, pool, state: SearchState, results_per_keyword: int = 7,
                 min_delay: float = 45.0, jitter: float = 0.5, cooldown_base: float = 300.0,
                 cooldown_cap: float = 21600.0, global_backoff_seconds: float = 21600.0,
                 quarantine_threshold: int = 0, quarantine_hours: float = 0.0,
                 reprobe_hours: float = 0.0, backoff_floor: float = 300.0,
                 ddgs_factory=DDGS, sleep=time.sleep, rand=random.random):
        self._pool = list(pool)
        self._state = state
        self._n = results_per_keyword
        self._delay = min_delay
        self._jitter = jitter
        self._base = cooldown_base
        self._cap = cooldown_cap
        self._global_backoff = global_backoff_seconds
        self._q_threshold = quarantine_threshold
        self._q_seconds = quarantine_hours * 3600
        self._reprobe_seconds = reprobe_hours * 3600
        self._backoff_floor = backoff_floor
        self._ddgs_factory = ddgs_factory
        self._sleep = sleep
        self._rand = rand

    def __call__(self, keyword: str, page: int = 1) -> list[SourceCandidate]:
        # last_served: did ANY backend genuinely respond this call (real results OR a
        # genuine empty)? False when every attempt was censored (block/backoff). Consumers
        # skip productivity accounting for censored phrases (a missing observation, not a
        # zero — see docs/superpowers/specs/2026-09-04-censoring-aware-discovery-design.md).
        self.last_served = False
        self._state.clear_degraded()
        if self._state.in_global_backoff():
            self._state.mark_degraded()
            return []
        for _ in range(2):  # at most two healthy backends per keyword
            backend = self._take_next_healthy()
            if backend is None:
                # all non-quarantined backends cooled → sleep only until the soonest recovers
                self._state.set_global_backoff(
                    self._state.soonest_recovery(self._pool, self._backoff_floor))
                self._state.mark_degraded()
                return []
            self._sleep(self._adaptive_delay() * (1 + self._rand() * self._jitter))
            try:
                results = self._ddgs_factory().text(keyword, max_results=self._n,
                                                    backend=backend, page=page)
            except Exception as exc:  # noqa: BLE001 — search is best-effort
                if _is_empty_result(exc):
                    # Backend answered fine, query just has zero hits (e.g. mojeek's tiny
                    # index vs a UA phrase). NOT a block: keep the backend healthy and let
                    # the keyword fall through to the next one.
                    log.debug("ddg backend %s empty for %r", backend, keyword)
                    self.last_served = True
                    self._state.record_success(backend)
                    continue
                log.warning("ddg backend %s failed for %r: %s", backend, keyword, exc)
                self._state.record_block(backend, self._base, self._cap, self._jitter, self._rand,
                                         quarantine_threshold=self._q_threshold,
                                         quarantine_seconds=self._q_seconds,
                                         reprobe_seconds=self._reprobe_seconds)
                continue
            self.last_served = True
            self._state.record_success(backend)
            return self._classify(results, backend, keyword)
        self._state.mark_degraded()
        return []

    def _adaptive_delay(self) -> float:
        """Base min_delay scaled by pool_size / healthy_count: fewer selectable
        backends → longer pause. At full health the multiplier is 1.0 (unchanged)."""
        healthy = sum(1 for b in self._pool if self._selectable(b))
        if healthy <= 0:
            return self._delay
        return self._delay * (len(self._pool) / healthy)

    def _selectable(self, backend: str) -> bool:
        if self._state.reprobe_due(backend):     # one low-frequency trial for a dead backend
            return True
        if self._state.is_quarantined(backend):  # quarantined & not due → skip
            return False
        return self._state.is_healthy(backend)   # normal transient cooldown check

    def _take_next_healthy(self) -> str | None:
        n = len(self._pool)
        if n == 0:
            return None
        start = self._state.cursor % n
        for offset in range(n):
            idx = (start + offset) % n
            backend = self._pool[idx]
            if self._selectable(backend):
                self._state.set_cursor((idx + 1) % n)
                return backend
        return None

    def _classify(self, results, backend: str, keyword: str) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        for r in results or []:
            classified = classify_candidate(r.get("href", ""))
            if classified is None:
                continue
            type_, url_or_handle = classified
            out.append(SourceCandidate(
                name=r.get("title") or url_or_handle, type=type_, url_or_handle=url_or_handle,
                discovered_from_source_id=None, discovery_note=f"ddg:{backend}: {keyword}"))
        return out


class SearchCache:
    """TTL decorator over a search provider. Cache hit = no network, no sleep.
    Does not cache a result produced while global backoff is (or becomes) active, or one the
    inner provider flagged as degraded (all attempted backends failed)."""

    def __init__(self, inner, state: SearchState, ttl_seconds: float):
        self._inner = inner
        self._state = state
        self._ttl = ttl_seconds

    def __call__(self, keyword: str, page: int = 1) -> list[SourceCandidate]:
        cached = self._state.cache_get(keyword, self._ttl, page)
        if cached is not None:
            self.last_served = True        # cached data is a served observation
            return cached
        if self._state.in_global_backoff():
            self.last_served = False       # short-circuit, nothing served
            return []
        results = self._inner(keyword, page)
        self.last_served = getattr(self._inner, "last_served", True)
        if self._state.in_global_backoff():        # inner just tripped backoff — degraded empty
            return []
        if self._state.degraded_last_call():       # inner flagged degraded — don't cache the empty
            return []
        self._state.cache_put(keyword, results, page)
        return results


class SearxngProvider:
    """Callable (keyword) -> list[SourceCandidate] via a self-hosted SearXNG JSON API.
    Independent of DDG: keeps its own consecutive-failure cooldown so a throttled SearXNG
    self-suppresses without touching the DDG SearchState global backoff."""

    def __init__(self, base_url: str, results_per_keyword: int = 7, min_delay: float = 4.0,
                 client_factory=None, sleep=time.sleep, clock=time.time,
                 fail_threshold: int = 3, cooldown_base: float = 300.0,
                 cooldown_cap: float = 3600.0, engines: str = ""):
        self._base = base_url.rstrip("/")
        self._n = results_per_keyword
        self._delay = min_delay
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=20))
        self._sleep = sleep
        self._clock = clock
        self._fail_threshold = fail_threshold
        self._cooldown_base = cooldown_base
        self._cooldown_cap = cooldown_cap
        self._engines = engines
        self._fails = 0
        self._cooldown_until = 0.0
        self._slice_ok = False
        self.last_served = False

    def available(self) -> bool:
        return self._clock() >= self._cooldown_until

    def succeeded(self) -> bool:
        return self._slice_ok

    def __call__(self, keyword: str, page: int = 1) -> list[SourceCandidate]:
        self._slice_ok = False
        self.last_served = False           # censored unless the HTTP call succeeds below
        if self._clock() < self._cooldown_until:
            return []
        if self._delay:
            self._sleep(self._delay)
        try:
            with self._client_factory() as client:
                params = {"q": keyword, "format": "json"}
                if int(page) > 1:
                    params["pageno"] = int(page)
                if self._engines:
                    params["engines"] = self._engines
                resp = client.get(f"{self._base}/search", params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — search is best-effort
            log.warning("searxng search failed for %r: %s", keyword, exc)
            self._fails += 1
            if self._fails >= self._fail_threshold:
                over = self._fails - self._fail_threshold
                self._cooldown_until = self._clock() + min(
                    self._cooldown_base * (2 ** over), self._cooldown_cap)
            return []
        self._fails = 0
        self._cooldown_until = 0.0
        self._slice_ok = True
        self.last_served = True            # HTTP 200 + parsed body = a served observation
        out: list[SourceCandidate] = []
        for r in (data.get("results") or [])[:self._n]:
            classified = classify_candidate(r.get("url", ""))
            if classified is None:
                continue
            type_, url_or_handle = classified
            out.append(SourceCandidate(
                name=r.get("title") or url_or_handle, type=type_, url_or_handle=url_or_handle,
                discovered_from_source_id=None, discovery_note=f"searxng: {keyword}"))
        return out


@dataclass
class SearchProviderPlan:
    """One search provider bound to its own ActiveDiscovery, per-pass success check,
    and forward-looking availability (health) predicate. Consumed by SearchPass."""
    name: str
    discovery: ActiveDiscovery
    include_pins: bool
    succeeded: Callable[[], bool]
    available: Callable[[], bool]


def build_search_plans(config, state=None) -> list[SearchProviderPlan]:
    """Build one plan per enabled search provider (no combine/fan-out)."""
    plans: list[SearchProviderPlan] = []
    budget = config.search_budget or 0        # 0 == unlimited (slice already bounds it)
    for name in config.search_providers:
        if name == "duckduckgo":
            if state is None:
                state = SearchState.load(config.search_state_path)
            rotating = RotatingDdgProvider(
                pool=config.search_backends, state=state,
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay, jitter=config.search_jitter,
                cooldown_base=config.search_backend_cooldown_base_seconds,
                cooldown_cap=config.search_backend_cooldown_cap_seconds,
                global_backoff_seconds=config.search_global_backoff_hours * 3600,
                quarantine_threshold=config.search_backend_quarantine_threshold,
                quarantine_hours=config.search_backend_quarantine_hours,
                reprobe_hours=config.search_backend_reprobe_hours,
                backoff_floor=config.search_backoff_floor_seconds)
            provider = SearchCache(rotating, state, config.search_cache_ttl_hours * 3600)
            plans.append(SearchProviderPlan(
                name="duckduckgo",
                discovery=ActiveDiscovery(budget=budget, search_provider=provider),
                include_pins=True,
                succeeded=(lambda st=state: not st.in_global_backoff()),
                available=(lambda st=state: not st.in_global_backoff())))
        elif name == "searxng":
            sx = SearxngProvider(config.searxng_url,
                                 results_per_keyword=config.search_results_per_keyword,
                                 min_delay=config.searxng_min_delay,
                                 engines=config.searxng_engines)
            plans.append(SearchProviderPlan(
                name="searxng",
                discovery=ActiveDiscovery(budget=budget, search_provider=sx),
                include_pins=True,
                succeeded=sx.succeeded,
                available=sx.available))
        else:
            log.warning("unknown search provider %r, ignoring", name)
    return plans
