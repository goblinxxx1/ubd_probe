import logging

import httpx

from crawler.accounts.pool import AccountPool
from crawler.api_client import ApiClient
from crawler.discovery.active import ActiveDiscovery
from crawler.discovery.brand_feed import (
    BRAND_SEEDS, BrandDomainCache, BrandFeed, BrandResolver, refresh_brand_domains)
from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.providers import build_search_provider
from crawler.discovery.query_grid import QueryGrid, merge_queries
from crawler.discovery.search_state import SearchState
from crawler.extract.base import get_extractor
from crawler.fetchers.facebook import FacebookFetcher
from crawler.fetchers.instagram import InstagramFetcher
from crawler.fetchers.telegram import TelegramFetcher
from crawler.fetchers.website import WebsiteFetcher
from crawler.ratelimit import RateLimiter
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
    return BrandFeed(cache, BRAND_SEEDS)


def build_runner(config) -> Runner:
    api = ApiClient(config.internal_api_url, config.crawler_api_key, config.request_timeout)

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
    if (discovery is not None or brand_feed is not None) and config.active_fetch_budget:
        harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                    fetch_budget=config.active_fetch_budget)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=keywords, harvester=harvester,
                  brand_feed=brand_feed, freshness_ttl_days=config.freshness_ttl_days)
