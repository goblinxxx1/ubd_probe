import logging

from crawler.discovery.attribution import attribute, build_page_ctx
from crawler.discovery.passive import normalize_ref
from crawler.payloads import offer_payload

log = logging.getLogger(__name__)

_FETCHABLE = ("website", "telegram")


def _as_source(cand) -> dict:
    return {"id": None, "type": cand.type, "url_or_handle": cand.url_or_handle,
            "name": cand.name}


class ActiveHarvester:
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20):
        self._api = api
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._budget = fetch_budget

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

    def _harvest_one(self, cand, fetcher, cats, known, summary) -> None:
        if self._rl is not None:
            self._rl.wait(cand.type)
        items, _ = fetcher.fetch(_as_source(cand), None)
        passing = [it for it in items
                   if self._extractor.extract(it, "", cats) is not None]
        ctx = build_page_ctx(cand, passing)
        for item in passing:
            attr = attribute(item, ctx)
            if attr is None:
                continue
            offer = self._extractor.extract(item, attr.provider, cats)
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
