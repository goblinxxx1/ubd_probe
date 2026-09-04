import logging

from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate

log = logging.getLogger(__name__)


class ActiveDiscovery:
    def __init__(self, budget: int, search_provider=None):
        self._budget = budget
        self._provider = search_provider

    def run(self, keywords: list[str], known: set[str],
            pages: dict[str, int] | None = None) -> list[SourceCandidate]:
        # Phrases whose search channel genuinely responded this pass (results OR a real
        # empty). A phrase left out was censored (block/backoff/error/budget-skipped);
        # consumers skip productivity accounting for it — a missing observation, not a zero.
        self.last_served_phrases: set[str] = set()
        if self._provider is None:
            return []
        pages = pages or {}
        out: list[SourceCandidate] = []
        seen: set[tuple[str, str]] = set()
        used = 0
        for kw in keywords:
            if self._budget and used >= self._budget:
                break
            used += 1
            try:
                results = self._provider(kw, pages.get(kw, 1))
            except Exception as exc:  # noqa: BLE001 — search is best-effort
                log.warning("active search failed for %r: %s", kw, exc)
                continue
            if getattr(self._provider, "last_served", True):
                self.last_served_phrases.add(kw)
            for c in results:
                ref = normalize_ref(c.type, c.url_or_handle)
                if ref in known or (c.type, ref) in seen:
                    continue
                seen.add((c.type, ref))
                out.append(c)
        return out
