import logging

from crawler.discovery.passive import extract_source_candidates, normalize_ref
from crawler.extract.base import CategoryIndex

log = logging.getLogger(__name__)


def offer_payload(cand) -> dict:
    return {
        "type": cand.offer_type,
        "title": cand.title,
        "description": cand.body,
        "provider": cand.provider,
        "discount_type": cand.discount_type,
        "discount_value": cand.discount_value,
        "valid_from": cand.valid_from.isoformat() if cand.valid_from else None,
        "valid_until": cand.valid_until.isoformat() if cand.valid_until else None,
        "source_id": cand.source_id,
        "content_hash": cand.content_hash,
        "target_category_ids": cand.target_category_ids,
        "offer_category_ids": cand.offer_category_ids,
    }


def suggestion_payload(sc) -> dict:
    return {
        "name": sc.name,
        "type": sc.type,
        "url_or_handle": sc.url_or_handle,
        "discovered_from_source_id": sc.discovered_from_source_id,
        "discovery_note": sc.discovery_note,
    }


class Runner:
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter

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
        summary = {"sources": 0, "offers": 0, "suggestions": 0, "errors": 0}

        for source in sources:
            summary["sources"] += 1
            try:
                self._crawl_source(source, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per source
                summary["errors"] += 1
                log.warning("source #%s failed: %s", source.get("id"), exc)
        log.info("crawl summary: %s", summary)
        return summary

    def _crawl_source(self, source, cats, known, summary):
        state = self._api.get_crawl_state(source["id"])
        items, new_key = self._fetch_for(source, state.get("last_seen_key"))
        for item in items:
            cand = self._extractor.extract(item, source["name"], cats)
            if cand is not None:
                self._api.submit_offer(offer_payload(cand))
                summary["offers"] += 1
            for sc in extract_source_candidates(item, known):
                self._api.submit_suggestion(suggestion_payload(sc))
                known.add(normalize_ref(sc.type, sc.url_or_handle))
                summary["suggestions"] += 1
        self._api.set_crawl_state(source["id"], new_key)
