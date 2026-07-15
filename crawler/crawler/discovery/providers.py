import logging
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

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


def build_search_provider(config):
    """Combine enabled search providers into one callable, or None."""
    providers = []
    for name in config.search_providers:
        if name == "duckduckgo":
            providers.append(DuckDuckGoProvider(
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
