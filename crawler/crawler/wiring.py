import logging

import httpx

from crawler.accounts.pool import AccountPool
from crawler.api_client import ApiClient
from crawler.discovery.active import ActiveDiscovery
from crawler.discovery import blocklist
from crawler.discovery.brand_feed import (
    BRAND_SEEDS, BrandDomainCache, BrandFeed, BrandResolver, refresh_brand_domains)
from crawler.discovery.domain_feed import DomainFeed
from crawler.discovery.domain_registry import DomainRegistry
from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.providers import build_search_provider
from crawler.discovery.query_grid import QueryGrid, merge_queries
from crawler.discovery.robots import RobotsPolicy
from crawler.discovery.search_state import SearchState
from crawler.discovery.walker import DomainWalker
from crawler.extract.base import get_extractor
from crawler.fetchers.facebook import FacebookFetcher
from crawler.fetchers.instagram import InstagramFetcher
from crawler.fetchers.telegram import TelegramFetcher
from crawler.fetchers.website import WebsiteFetcher
from crawler.ratelimit import DomainRateLimiter, RateLimiter
from crawler.runner import Runner

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; UBDCrawler/0.1; +https://ubd.example)"


def _http_client(timeout: float, proxy: str | None = None) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": _UA},
                        proxy=proxy, follow_redirects=True)


def _build_brand_feed(config):
    cache = BrandDomainCache.load(config.brand_domains_path)
    if cache.is_stale(config.brand_feed_refresh_hours * 3600):
        try:
            resolver = BrandResolver(overpass_url=config.overpass_url,
                                     wikidata_url=config.wikidata_url,
                                     timeout=config.request_timeout)
            refresh_brand_domains(cache, resolver, BRAND_SEEDS)
        except Exception as exc:  # noqa: BLE001 — refresh is best-effort; feed uses cache/fallbacks
            log.warning("brand-domain refresh failed: %s", exc)
    return BrandFeed(cache, BRAND_SEEDS, per_pass=config.brand_feed_per_pass)


def _build_walker(config, web_client):
    domain_rl = DomainRateLimiter(config.domain_min_delay_seconds)
    robots = RobotsPolicy(web_client, domain_rl, config.robots_cache_path,
                          config.robots_cache_ttl_hours * 3600)
    walker = DomainWalker(
        web_client, robots, domain_rl,
        domain_page_cap=config.domain_page_cap,
        sitemap_max_docs=config.sitemap_max_docs,
        bfs_max_depth=config.bfs_max_depth,
        bfs_max_pages=config.bfs_max_pages,
        bfs_trigger_min=config.bfs_trigger_min,
        domain_min_delay=config.domain_min_delay_seconds,
        crawl_delay_cap=config.crawl_delay_cap_seconds)
    return walker, domain_rl


def build_runner(config) -> Runner:
    api = ApiClient(config.internal_api_url, config.crawler_api_key, config.request_timeout)

    if config.blocked_hosts_fetch_enabled:
        try:
            blocklist.reload_learned(api.list_blocked_hosts())
        except Exception as exc:  # noqa: BLE001 — learned-host fetch is best-effort
            log.warning("blocked-hosts fetch failed: %s", exc)

    web_client = _http_client(config.request_timeout)
    ig_creds = [c for c in config.bot_accounts if c.platform == "instagram"]
    fb_creds = [c for c in config.bot_accounts if c.platform == "facebook"]
    ig_pool = AccountPool("instagram", ig_creds, api)
    fb_pool = AccountPool("facebook", fb_creds, api)

    fetchers = {
        "website": WebsiteFetcher(web_client),
        "telegram": TelegramFetcher(web_client),
        "instagram": InstagramFetcher(ig_pool, _http_client(config.request_timeout,
                                                             config.proxies.get("instagram"))),
        "facebook": FacebookFetcher(fb_pool, _http_client(config.request_timeout,
                                                          config.proxies.get("facebook"))),
    }
    extractor = get_extractor(config.extractor)
    rate_limiter = RateLimiter(config.min_delay_seconds)

    discovery = None
    harvester = None
    brand_feed = None
    keywords = config.search_keywords
    if config.active_discovery:
        state = SearchState.load(config.search_state_path)
        batch, new_cursor = QueryGrid().next_batch(
            config.search_queries_per_pass, state.grid_cursor)
        state.set_grid_cursor(new_cursor)
        keywords = merge_queries(batch, config.search_keywords)
        provider = build_search_provider(config, state=state)
        if provider is not None:
            budget = config.search_budget or len(keywords)
            discovery = ActiveDiscovery(budget=budget, search_provider=provider)
    if config.brand_feed_enabled:
        brand_feed = _build_brand_feed(config)
    walker = None
    domain_rl = None
    if config.sitemap_depth_enabled:
        walker, domain_rl = _build_walker(config, web_client)

    domain_registry = None
    domain_feed = None
    if config.domain_rating_enabled:
        domain_registry = DomainRegistry.load(
            config.domain_registry_path,
            decay=config.domain_score_decay,
            offer_weight=config.domain_offer_weight,
            error_weight=config.domain_error_weight,
            promote_min_score=config.domain_promote_min_score)
        domain_feed = DomainFeed(domain_registry, per_pass=config.domain_feed_per_pass)
        if walker is None:
            walker, domain_rl = _build_walker(config, web_client)   # passive deep-walk needs it

    corpus_recorder = None
    if config.autofill_enabled:
        from crawler.discovery import promo_lexicon
        from crawler.learn.corpus import CorpusRecorder
        from crawler.learn.snowball import SnowballIngestor

        promo_lexicon.reload_learned(config.promo_lexicon_learned_path)
        corpus_recorder = CorpusRecorder(config.corpus_path, config.corpus_max_mb)
        try:
            SnowballIngestor(api, corpus_recorder, config.snowball_state_path).ingest()
        except Exception as exc:  # noqa: BLE001 — snowball best-effort
            log.warning("snowball ingest failed: %s", exc)

    if (discovery is not None or brand_feed is not None) and config.active_fetch_budget:
        harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                    fetch_budget=config.active_fetch_budget,
                                    walker=walker, domain_rate_limiter=domain_rl,
                                    corpus_recorder=corpus_recorder,
                                    domain_registry=domain_registry,
                                    hardening_enabled=config.attribution_hardening_enabled)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=keywords, harvester=harvester,
                  brand_feed=brand_feed, freshness_ttl_days=config.freshness_ttl_days,
                  corpus_recorder=corpus_recorder,
                  walker=walker, domain_rate_limiter=domain_rl,
                  domain_feed=domain_feed, domain_registry=domain_registry,
                  domain_evict_min_score=config.domain_evict_min_score,
                  domain_evict_ttl_seconds=config.domain_evict_ttl_hours * 3600)
