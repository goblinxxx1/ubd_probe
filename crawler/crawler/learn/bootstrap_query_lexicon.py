"""One-shot bootstrap: pull ALL approved offers, feed their texts into the corpus,
seed structural offer_categories directly into the LEARNED query lexicon (moderator-
vetted → no audit), then run the text-noun query miner. Idempotent."""

import json
import os
import time

from crawler.learn.query_stoplist import unstop
from crawler.learn.run_query_miner import run_query_miner
from crawler.models import RawItem


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _seed_categories(learned_path, stoplist_path, cats) -> int:
    learned = _load(learned_path, [])
    have = {e.get("term") for e in learned}
    n = 0
    for c in cats:
        unstop(c, stoplist_path)                       # categories > stoplist
        if c not in have:
            learned.append({"term": c, "source": "category",
                            "approved_at": int(time.time())})
            have.add(c)
            n += 1
    _save(learned_path, learned)
    return n


def bootstrap(config, api, recorder) -> tuple[int, int]:
    rows = api.list_approved_offers(since=None) or []
    cats: list[str] = []
    for row in rows:
        item = RawItem(source_id=0, platform="website", key="bootstrap",
                       text=row.get("text", ""),
                       url=f"https://{row.get('host', '')}")
        recorder.record(item, True, snowball=True)
        for c in row.get("categories", []) or []:
            if c and c not in cats:
                cats.append(c)
    n_cat = _seed_categories(config.query_lexicon_learned_path,
                             config.query_stoplist_path, cats)
    n_cand = run_query_miner(config)
    return n_cat, n_cand


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    import logging

    from crawler.api_client import ApiClient
    from crawler.config import load_config
    from crawler.learn.corpus import CorpusRecorder

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    api = ApiClient(cfg.internal_api_url, cfg.crawler_api_key, cfg.request_timeout)
    rec = CorpusRecorder(cfg.corpus_path, cfg.corpus_max_mb)
    n_cat, n_cand = bootstrap(cfg, api, rec)
    print(f"seeded categories: {n_cat}; query candidates: {n_cand}")
