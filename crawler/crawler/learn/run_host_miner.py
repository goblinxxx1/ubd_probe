"""Офлайн-оркестратор host-blocklist: корпус → host_miner → host_vetoes → сабміт кандидатів
у backend (audit-черга). Дзеркало run_miner.py. protected_hosts подає викликач."""

from crawler.learn.corpus import read_corpus
from crawler.learn.host_miner import mine_hosts
from crawler.learn.host_vetoes import survivors
from crawler.util.hosts import bare_host


def run_host_miner(config, api, protected_hosts) -> int:
    rows = read_corpus(config.corpus_path)
    scores = mine_hosts(rows, aggregator_min_outbound=config.aggregator_min_outbound)
    protected = {bare_host(h) for h in (protected_hosts or set())}
    keep = survivors(scores, protected_hosts=protected,
                     min_support=config.host_miner_min_support,
                     media_min=config.host_miner_media_min,
                     aggregator_min=config.host_miner_aggregator_min,
                     max_candidates=config.host_miner_max_candidates)
    for s in keep:
        api.submit_host_candidate({
            "host": s.host, "media_ratio": s.media_ratio,
            "aggregator_ratio": s.aggregator_ratio, "support": s.support,
            "sample_urls": s.sample_urls,
        })
    return len(keep)


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    import logging

    from crawler.api_client import ApiClient
    from crawler.config import load_config

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    with ApiClient(cfg.internal_api_url, cfg.crawler_api_key, cfg.request_timeout) as api:
        protected = {s["url_or_handle"] for s in api.list_sources(is_active=True)}
        n = run_host_miner(cfg, api, protected)
    print(f"host candidates submitted: {n}")
