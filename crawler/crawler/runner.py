import logging

from crawler.discovery.passive import extract_source_candidates, normalize_ref
from crawler.extract.base import CategoryIndex
from crawler.extract.categories import resolve_offer_categories
from crawler.models import SourceCandidate
from crawler.payloads import offer_payload, suggestion_payload

log = logging.getLogger(__name__)


class Runner:
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter,
                 discovery=None, keywords=None, harvester=None, brand_feed=None,
                 freshness_ttl_days=30, corpus_recorder=None,
                 walker=None, domain_rate_limiter=None):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._discovery = discovery
        self._keywords = keywords or []
        self._harvester = harvester
        self._brand_feed = brand_feed
        self._freshness_ttl_days = freshness_ttl_days
        self._corpus = corpus_recorder
        self._walker = walker
        self._domain_rl = domain_rate_limiter

    def _fetch_for(self, source: dict, last_seen_key):
        fetcher = self._fetchers.get(source["type"])
        if fetcher is None:
            return [], last_seen_key
        self._rl.wait(source["type"])
        return fetcher.fetch(source, last_seen_key)

    def run(self) -> dict:
        cats = CategoryIndex(self._api.list_target_categories(),
                             self._api.list_offer_categories())
        sources = self._api.list_sources(is_active=True)
        known = {normalize_ref(s["type"], s["url_or_handle"]) for s in sources}
        summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}

        for source in sources:
            summary["sources"] += 1
            try:
                self._crawl_source(source, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per source
                summary["errors"] += 1
                log.warning("source #%s failed: %s", source.get("id"), exc)

        if self._harvester is not None:
            try:
                candidates = []
                if self._discovery is not None and self._keywords:
                    candidates += self._discovery.run(self._keywords, known)
                if self._brand_feed is not None:
                    candidates += self._brand_feed.candidates(known)
                if candidates:
                    self._harvester.harvest(candidates, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — discovery must not crash the pass
                summary["errors"] += 1
                log.warning("active discovery / brand-feed harvest failed: %s", exc)

        try:
            result = self._api.expire_stale(self._freshness_ttl_days)
            summary["expired"] = result.get("expired", 0)
        except Exception as exc:  # noqa: BLE001 — sweep must not crash the pass
            summary["errors"] += 1
            log.warning("expire-stale failed: %s", exc)

        log.info("crawl summary: %s", summary)
        return summary

    def _crawl_source(self, source, cats, known, summary):
        if self._walker is not None and source["type"] == "website":
            self._crawl_website_deep(source, cats, known, summary)
            return
        state = self._api.get_crawl_state(source["id"])
        items, new_key = self._fetch_for(source, state.get("last_seen_key"))
        for item in items:
            self._process_item(item, source, cats, known, summary)
        self._api.set_crawl_state(source["id"], new_key)

    def _crawl_website_deep(self, source, cats, known, summary):
        cand = SourceCandidate(name=source["name"], type="website",
                               url_or_handle=source["url_or_handle"])
        plan = self._walker.walk(cand)
        fetcher = self._fetchers.get("website")
        if fetcher is None:
            return
        state = self._api.get_crawl_state(source["id"])
        last_key = state.get("last_seen_key")
        for url in plan.urls:
            self._domain_rl.wait(plan.domain, plan.crawl_delay)
            page_src = {"id": source["id"], "type": "website",
                        "name": source["name"], "url_or_handle": url}
            items, last_key = fetcher.fetch(page_src, last_key)
            for item in items:
                self._process_item(item, source, cats, known, summary)
        self._api.set_crawl_state(source["id"], last_key)

    def _process_item(self, item, source, cats, known, summary):
        cand = self._extractor.extract(item, source["name"], cats)
        if self._corpus is not None:
            self._corpus.record(item, cand is not None)
        if cand is not None:
            cand.offer_category_ids = resolve_offer_categories(
                self._api, cats, cand.offer_category_matches)
            self._api.submit_offer(offer_payload(cand))
            summary["offers"] += 1
        for sc in extract_source_candidates(item, known):
            self._api.submit_suggestion(suggestion_payload(sc))
            known.add(normalize_ref(sc.type, sc.url_or_handle))
            summary["suggestions"] += 1
