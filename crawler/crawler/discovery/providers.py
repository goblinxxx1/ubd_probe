import logging
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
from ddgs import DDGS

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


class DuckDuckGoProvider:
    """Callable (keyword) -> list[SourceCandidate]; best-effort."""

    def __init__(self, results_per_keyword: int = 7, min_delay: float = 4.0,
                 ddgs_factory=DDGS, sleep=time.sleep):
        self._n = results_per_keyword
        self._delay = min_delay
        self._ddgs_factory = ddgs_factory
        self._sleep = sleep

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        if self._delay:
            self._sleep(self._delay)
        try:
            results = self._ddgs_factory().text(keyword, max_results=self._n)
        except Exception as exc:  # noqa: BLE001 — search is best-effort
            log.warning("duckduckgo search failed for %r: %s", keyword, exc)
            return []
        out: list[SourceCandidate] = []
        for r in results or []:
            url = _normalize_url(r.get("href", ""))
            if not url:
                continue
            out.append(SourceCandidate(
                name=r.get("title") or url, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"ddg: {keyword}"))
        return out


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
            url = _normalize_url(r.get("url", ""))
            if not url:
                continue
            out.append(SourceCandidate(
                name=r.get("title") or url, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"searxng: {keyword}"))
        return out


def build_search_provider(config):
    """Combine enabled search providers into one callable, or None."""
    providers = []
    for name in config.search_providers:
        if name == "duckduckgo":
            providers.append(DuckDuckGoProvider(
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay))
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
