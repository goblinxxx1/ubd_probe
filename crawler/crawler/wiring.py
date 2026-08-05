import logging

import httpx

from crawler.accounts.pool import AccountPool
from crawler.api_client import ApiClient
from crawler.discovery.aggregator_feed import AggregatorDomainFeed, AggregatorDomainStore
from crawler.discovery import blocklist
from crawler.discovery.brand_feed import (
    BRAND_SEEDS, BrandDomainCache, BrandFeed, BrandResolver, refresh_brand_domains)
from crawler.discovery.domain_feed import DomainFeed
from crawler.discovery.domain_registry import DomainRegistry
from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.osm_feed import OsmDomainFeed, OsmEnumerator
from crawler.discovery.providers import build_search_plans
from crawler.discovery import query_lexicon
from crawler.discovery.search_pass import SearchPass
from crawler.discovery.query_grid import QueryGrid, build_grid
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
from crawler.schedule import PassiveSchedule

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


def _build_osm_feed(config):
    cache = BrandDomainCache.load(config.osm_domains_path)
    if cache.is_stale(config.osm_feed_refresh_hours * 3600):
        try:
            domains = OsmEnumerator(
                overpass_url=config.overpass_url, timeout=config.osm_feed_query_timeout,
                min_pois=config.osm_min_pois,
                max_domains=config.osm_feed_max_domains).enumerate()
            if domains:
                cache.replace(domains)
        except Exception as exc:  # noqa: BLE001 — refresh best-effort; feed uses cache
            log.warning("osm-domain enumeration failed: %s", exc)
    return OsmDomainFeed(cache, per_pass=config.osm_feed_per_pass)


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
    extractor = get_extractor(config.extractor, require_discount=config.require_discount)
    rate_limiter = RateLimiter(config.min_delay_seconds)

    discovery = None
    search_pass = None
    harvester = None
    brand_feed = None
    state = None
    if config.active_discovery:
        state = SearchState.load(config.search_state_path)
        plans = build_search_plans(config, state=state)
        if plans:
            if config.query_lexicon_enabled:
                query_lexicon.reload_learned(config.query_lexicon_learned_path)
                services = list(query_lexicon.learned_services())[:config.query_lexicon_max_terms]
            else:
                query_lexicon.reload_learned(None)
                services = []
            cities = None if config.grid_cities_enabled else []
            grid = QueryGrid(build_grid(cities=cities, services=services))
            search_pass = SearchPass(plans, state, grid,
                                     config.search_block_size, config.search_keywords,
                                     ttl_seconds=config.search_cache_ttl_hours * 3600)
            discovery = search_pass.provider_for_site_query()   # DDG discovery for site: queries
    if config.brand_feed_enabled:
        brand_feed = _build_brand_feed(config)
    osm_feed = None
    if config.osm_feed_enabled:
        osm_feed = _build_osm_feed(config)
    aggregator_store = None
    aggregator_feed = None
    if config.aggregator_feed_enabled:
        aggregator_store = AggregatorDomainStore.load(config.aggregator_domains_path)
        aggregator_feed = AggregatorDomainFeed(
            aggregator_store, per_pass=config.aggregator_feed_per_pass)
    walker = None
    domain_rl = None
    if config.sitemap_depth_enabled:
        walker, domain_rl = _build_walker(config, web_client)

    domain_registry = None
    revisit_cooldown = config.active_revisit_cooldown_days * 86400
    domain_feed = None
    if config.domain_rating_enabled:
        domain_registry = DomainRegistry.load(
            config.domain_registry_path,
            decay=config.domain_score_decay,
            offer_weight=config.domain_offer_weight,
            error_weight=config.domain_error_weight,
            promote_min_score=config.domain_promote_min_score)
        domain_feed = DomainFeed(domain_registry, per_pass=config.domain_feed_per_pass,
                                 cooldown_seconds=revisit_cooldown)
        if walker is None:
            walker, domain_rl = _build_walker(config, web_client)   # passive deep-walk needs it

    site_planner = None
    site_state = None
    if config.site_query_enabled:
        from crawler.discovery.site_query import SiteQueryPlanner
        site_planner = SiteQueryPlanner()
        site_state = state if config.active_discovery else None   # rotate only when search runs

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

    if ((search_pass is not None or brand_feed is not None
         or osm_feed is not None or domain_feed is not None
         or aggregator_feed is not None)
            and config.active_fetch_budget):
        harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                    fetch_budget=config.active_fetch_budget,
                                    walker=walker, domain_rate_limiter=domain_rl,
                                    corpus_recorder=corpus_recorder,
                                    domain_registry=domain_registry,
                                    hardening_enabled=config.attribution_hardening_enabled,
                                    aggregator_min_outbound=config.aggregator_min_outbound,
                                    aggregator_store=aggregator_store,
                                    aggregator_max_domains=config.aggregator_max_domains,
                                    revisit_cooldown_seconds=revisit_cooldown)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, search_pass=search_pass, harvester=harvester,
                  brand_feed=brand_feed, freshness_ttl_days=config.freshness_ttl_days,
                  corpus_recorder=corpus_recorder,
                  walker=walker, domain_rate_limiter=domain_rl,
                  domain_feed=domain_feed, domain_registry=domain_registry,
                  domain_evict_min_score=config.domain_evict_min_score,
                  domain_evict_ttl_seconds=config.domain_evict_ttl_hours * 3600,
                  site_planner=site_planner, site_state=site_state,
                  site_query_budget=config.site_query_budget,
                  osm_feed=osm_feed, aggregator_feed=aggregator_feed,
                  passive_schedule=PassiveSchedule(config.passive_state_path,
                                                   config.passive_interval_seconds),
                  revisit_cooldown_seconds=revisit_cooldown)
