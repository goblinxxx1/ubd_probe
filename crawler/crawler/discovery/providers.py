import logging
import random
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
from ddgs import DDGS

from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate

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


_IG_RESERVED = ("/p/", "/reel/", "/reels/", "/explore/", "/stories/")
_FB_RESERVED = ("/share", "/sharer", "/events", "/photo", "/watch")


def classify_candidate(url: str) -> tuple[str, str] | None:
    """Map a search-result URL to (source_type, url_or_handle), or None to skip."""
    norm = _normalize_url(url)
    if not norm:
        return None
    parts = urlsplit(norm)
    host = parts.netloc.lower().removeprefix("www.")
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
    backoff and returns []. Best-effort: never raises for a single keyword.
    """

    def __init__(self, pool, state: SearchState, results_per_keyword: int = 7,
                 min_delay: float = 45.0, jitter: float = 0.5, cooldown_base: float = 300.0,
                 cooldown_cap: float = 21600.0, global_backoff_seconds: float = 21600.0,
                 ddgs_factory=DDGS, sleep=time.sleep, rand=random.random):
        self._pool = list(pool)
        self._state = state
        self._n = results_per_keyword
        self._delay = min_delay
        self._jitter = jitter
        self._base = cooldown_base
        self._cap = cooldown_cap
        self._global_backoff = global_backoff_seconds
        self._ddgs_factory = ddgs_factory
        self._sleep = sleep
        self._rand = rand

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        if self._state.in_global_backoff():
            return []
        for _ in range(2):  # at most two healthy backends per keyword
            backend = self._take_next_healthy()
            if backend is None:
                self._state.set_global_backoff(self._global_backoff)
                return []
            self._sleep(self._delay * (1 + self._rand() * self._jitter))
            try:
                results = self._ddgs_factory().text(keyword, max_results=self._n, backend=backend)
            except Exception as exc:  # noqa: BLE001 — search is best-effort
                log.warning("ddg backend %s failed for %r: %s", backend, keyword, exc)
                self._state.record_block(backend, self._base, self._cap, self._jitter, self._rand)
                continue
            self._state.record_success(backend)
            return self._classify(results, backend, keyword)
        return []

    def _take_next_healthy(self) -> str | None:
        n = len(self._pool)
        if n == 0:
            return None
        start = self._state.cursor % n
        for offset in range(n):
            idx = (start + offset) % n
            backend = self._pool[idx]
            if self._state.is_healthy(backend):
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
    Does not cache a result produced while global backoff is (or becomes) active."""

    def __init__(self, inner, state: SearchState, ttl_seconds: float):
        self._inner = inner
        self._state = state
        self._ttl = ttl_seconds

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        cached = self._state.cache_get(keyword, self._ttl)
        if cached is not None:
            return cached
        if self._state.in_global_backoff():
            return []
        results = self._inner(keyword)
        if self._state.in_global_backoff():   # inner just tripped backoff — degraded empty
            return []
        self._state.cache_put(keyword, results)
        return results


class SearxngProvider:
    """Callable (keyword) -> list[SourceCandidate]; best-effort, via SearXNG JSON API."""

    def __init__(self, base_url: str, results_per_keyword: int = 7, min_delay: float = 4.0,
                 client_factory=None, sleep=time.sleep):
        self._base = base_url.rstrip("/")
        self._n = results_per_keyword
        self._delay = min_delay
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=20))
        self._sleep = sleep

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        if self._delay:
            self._sleep(self._delay)
        try:
            with self._client_factory() as client:
                resp = client.get(f"{self._base}/search",
                                  params={"q": keyword, "format": "json"})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — search is best-effort
            log.warning("searxng search failed for %r: %s", keyword, exc)
            return []
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


def build_search_provider(config):
    """Combine enabled search providers into one callable, or None."""
    providers = []
    state = None
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
                global_backoff_seconds=config.search_global_backoff_hours * 3600)
            providers.append(SearchCache(rotating, state,
                                         config.search_cache_ttl_hours * 3600))
        elif name == "searxng":
            providers.append(SearxngProvider(
                base_url=config.searxng_url,
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay))
        else:
            log.warning("unknown search provider %r, ignoring", name)
    if not providers:
        return None

    def combined(keyword):
        out = []
        for p in providers:
            out.extend(p(keyword))
        return out

    return combined
