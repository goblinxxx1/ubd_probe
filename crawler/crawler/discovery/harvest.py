import logging

from crawler.discovery.attribution import attribute, build_page_ctx
from crawler.discovery.passive import normalize_ref
from crawler.extract.categories import resolve_offer_categories
from crawler.payloads import offer_payload

log = logging.getLogger(__name__)

_FETCHABLE = ("website", "telegram")


class ActiveHarvester:
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20,
                 walker=None, domain_rate_limiter=None, corpus_recorder=None):
        self._api = api
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._budget = fetch_budget
        self._walker = walker
        self._domain_rl = domain_rate_limiter
        self._corpus = corpus_recorder

    def harvest(self, candidates, cats, known, summary) -> None:
        used = 0
        for cand in candidates:
            if used >= self._budget:
                break
            if cand.type not in _FETCHABLE:
                continue
            if normalize_ref(cand.type, cand.url_or_handle) in known:
                continue
            fetcher = self._fetchers.get(cand.type)
            if fetcher is None:
                continue
            used += 1
            try:
                self._harvest_one(cand, fetcher, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per candidate
                summary["errors"] += 1
                log.warning("active harvest failed for %s: %s", cand.url_or_handle, exc)

    def _plan(self, cand):
        """(urls, domain, delay) for a candidate. Website candidates expand via the walker."""
        if self._walker is not None and cand.type == "website":
            plan = self._walker.walk(cand)
            return plan.urls, plan.domain, plan.crawl_delay
        return [cand.url_or_handle], None, None

    def _wait(self, cand_type, domain, delay) -> None:
        if domain is not None and self._domain_rl is not None:
            self._domain_rl.wait(domain, delay)
        elif self._rl is not None:
            self._rl.wait(cand_type)

    def _harvest_one(self, cand, fetcher, cats, known, summary) -> None:
        urls, domain, delay = self._plan(cand)
        for url in urls:
            self._wait(cand.type, domain, delay)
            src = {"id": None, "type": cand.type, "url_or_handle": url, "name": cand.name}
            try:
                items, _ = fetcher.fetch(src, None)
                self._process_page(cand, items, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — one page must not sink the domain
                summary["errors"] += 1
                log.warning("harvest page failed for %s: %s", url, exc)

    def _process_page(self, cand, items, cats, known, summary) -> None:
        passing = []
        for it in items:
            is_offer = self._extractor.extract(it, "", cats) is not None
            if self._corpus is not None:
                self._corpus.record(it, is_offer)
            if is_offer:
                passing.append(it)
        ctx = build_page_ctx(cand, passing)
        for item in passing:
            attr = attribute(item, ctx)
            if attr is None:
                continue
            offer = self._extractor.extract(item, attr.provider, cats)
            offer.offer_category_ids = resolve_offer_categories(
                self._api, cats, offer.offer_category_matches)
            self._api.submit_offer(offer_payload(offer))
            summary["offers"] += 1
            if attr.suggest_url_or_handle:
                s_ref = normalize_ref(attr.suggest_type, attr.suggest_url_or_handle)
                if s_ref not in known:
                    self._api.submit_suggestion({
                        "name": attr.suggest_name,
                        "type": attr.suggest_type,
                        "url_or_handle": attr.suggest_url_or_handle,
                        "discovered_from_source_id": None,
                        "discovery_note": f"active-search offer from {cand.url_or_handle}",
                    })
                    known.add(s_ref)
                    summary["suggestions"] += 1
