import logging

from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate

log = logging.getLogger(__name__)


class ActiveDiscovery:
    def __init__(self, budget: int, search_provider=None):
        self._budget = budget
        self._provider = search_provider

    def run(self, keywords: list[str], known: set[str]) -> list[SourceCandidate]:
        if self._provider is None:
            return []
        out: list[SourceCandidate] = []
        seen: set[tuple[str, str]] = set()
        used = 0
        for kw in keywords:
            if used >= self._budget:
                break
            used += 1
            try:
                results = self._provider(kw)
            except Exception as exc:  # noqa: BLE001 — search is best-effort
                log.warning("active search failed for %r: %s", kw, exc)
                continue
            for c in results:
                ref = normalize_ref(c.type, c.url_or_handle)
                if ref in known or (c.type, ref) in seen:
                    continue
                seen.add((c.type, ref))
                out.append(c)
        return out
