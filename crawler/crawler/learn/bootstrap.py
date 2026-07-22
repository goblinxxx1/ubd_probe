"""Одноразовий наповнювач корпусу: website-фетч + walker по brand-feed доменах,
щоб майнер мав дані вже до перших живих прогонів."""

import logging

from crawler.extract.base import CategoryIndex, get_extractor
from crawler.learn.corpus import CorpusRecorder

log = logging.getLogger(__name__)


def bootstrap(config, limit=None) -> int:
    if not getattr(config, "brand_feed_enabled", False):
        return 0
    from crawler.fetchers.website import WebsiteFetcher
    from crawler.wiring import _build_brand_feed, _build_walker, _http_client

    client = _http_client(config.request_timeout)
    feed = _build_brand_feed(config)
    walker, _ = _build_walker(config, client)
    fetcher = WebsiteFetcher(client)
    extractor = get_extractor(config.extractor)
    recorder = CorpusRecorder(config.corpus_path, config.corpus_max_mb)
    cats = CategoryIndex(target=[], offer=[])

    n = 0
    cands = feed.candidates(set())
    for cand in (cands[:limit] if limit else cands):
        try:
            plan = walker.walk(cand)
            for url in plan.urls:
                src = {"id": None, "type": "website", "url_or_handle": url, "name": cand.name}
                items, _ = fetcher.fetch(src, None)
                for it in items:
                    recorder.record(it, extractor.extract(it, "", cats) is not None)
                    n += 1
        except Exception as exc:  # noqa: BLE001 — best-effort
            log.warning("bootstrap failed for %s: %s", cand.url_or_handle, exc)
    return n


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    from crawler.config import load_config

    logging.basicConfig(level=logging.INFO)
    n = bootstrap(load_config())
    print(f"corpus rows recorded: {n}")
