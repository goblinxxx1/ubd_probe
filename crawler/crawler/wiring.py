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
from crawler.discovery.geo_block import GeoBlockStore
from crawler.discovery.lang_block import LangBlockStore
from crawler.discovery.language_gate import LanguageGate
from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.osm_feed import OsmDomainFeed, OsmEnumerator
from crawler.discovery.providers import build_search_plans
from crawler.discovery import query_grid, query_lexicon
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
from crawler.judge.base import NullJudge
from crawler.judge.cache import VerdictCache
from crawler.judge.gate import RelevanceGate
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
    language_gate = (LanguageGate(web_client, domain_rl)
                     if config.lang_gate_enabled else None)
    walker = DomainWalker(
        web_client, robots, domain_rl,
        domain_page_cap=config.domain_page_cap,
        sitemap_max_docs=config.sitemap_max_docs,
        bfs_max_depth=config.bfs_max_depth,
        bfs_max_pages=config.bfs_max_pages,
        bfs_trigger_min=config.bfs_trigger_min,
        domain_min_delay=config.domain_min_delay_seconds,
        crawl_delay_cap=config.crawl_delay_cap_seconds,
        language_gate=language_gate)
    return walker, domain_rl


def build_query_grid(config) -> QueryGrid:
    """Materialize the DDG query grid from the CURRENT lexicon file. Called at
    build_runner time AND on each in-loop learn tick, so freshly learned service
    terms go live without a process restart. Kill-switch (`query_lexicon_enabled`
    off) suppresses seed + learned alike, leaving the byte-stable base+geo grid."""
    if config.query_lexicon_enabled:
        query_lexicon.reload_learned(config.query_lexicon_learned_path)
        # curated seed always in; miner uncapped by default (cap<=0), so
        # self-learning never hits a ceiling — cap>0 trims the mined tail only.
        services = query_lexicon.compose_service_terms(
            query_grid.SEED_SERVICES, config.query_lexicon_max_terms)
    else:
        query_lexicon.reload_learned(None)
        services = []   # kill-switch suppresses seed + learned alike
    cities = None if config.grid_cities_enabled else []
    return QueryGrid(build_grid(cities=cities, services=services))


def build_runner(config) -> Runner:
    api = ApiClient(config.internal_api_url, config.crawler_api_key, config.request_timeout)

    if config.blocked_hosts_fetch_enabled:
        try:
            blocklist.reload_learned(api.list_blocked_hosts())
        except Exception as exc:  # noqa: BLE001 — learned-host fetch is best-effort
            log.warning("blocked-hosts fetch failed: %s", exc)

    # Persistent RU/BY geo-block (path/subdomain signal → whole host). load() pushes the
    # set into blocklist so is_blocked_host drops these hosts everywhere from the start.
    geo_block_store = GeoBlockStore(config.geo_blocked_hosts_path).load()
    lang_block_store = (LangBlockStore(config.lang_blocked_hosts_path).load()
                        if config.lang_gate_enabled else None)

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
            grid = build_query_grid(config)
            search_pass = SearchPass(plans, state, grid,
                                     config.search_block_size, config.search_keywords,
                                     ttl_seconds=config.search_cache_ttl_hours * 3600,
                                     page_cap=config.active_search_page_cap)
            # Static fallback for the site: leg's discovery (used only when search_pass is None);
            # run_active recomputes the live provider each pass via provider_for_site_query().
            discovery = search_pass.provider_for_site_query()   # first available provider (DDG at wiring time)
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
            promote_min_score=config.domain_promote_min_score,
            reject_weight=config.domain_reject_weight,
            empty_skip=config.domain_empty_skip_crawls)
        domain_feed = DomainFeed(domain_registry, per_pass=config.domain_feed_per_pass,
                                 cooldown_seconds=revisit_cooldown)
        if walker is None:
            walker, domain_rl = _build_walker(config, web_client)   # passive deep-walk needs it

    reject_ingestor = None
    if config.domain_rating_enabled and config.rejection_feedback_enabled:
        from crawler.learn.reject_feedback import RejectionIngestor
        reject_ingestor = RejectionIngestor(api, domain_registry,
                                            config.reject_since_state_path)

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

    media_blocker = None
    if domain_registry is not None and config.media_autoblock_enabled:
        from crawler.discovery.media_autoblock import MediaAutoBlocker
        media_blocker = MediaAutoBlocker(api)

    if config.judge_enabled and config.judge_url:
        from crawler.judge.llama import LlamaCppJudge
        judge = LlamaCppJudge(httpx.Client(base_url=config.judge_url),
                              model=config.judge_model,
                              timeout=config.judge_timeout_seconds)
    else:
        judge = NullJudge()
    relevance_gate = RelevanceGate(judge, VerdictCache(config.judge_cache_path),
                                   enabled=config.judge_enabled)

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
                                    revisit_cooldown_seconds=revisit_cooldown,
                                    geo_block_store=geo_block_store,
                                    media_blocker=media_blocker,
                                    media_autoblock_crawls=config.media_autoblock_crawls,
                                    lang_block_store=lang_block_store,
                                    editorial_gate_enabled=config.editorial_gate_enabled,
                                    source_hint_enabled=config.source_hint_enabled,
                                    active_workers=config.active_workers,
                                    relevance_gate=relevance_gate)
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
                  revisit_cooldown_seconds=revisit_cooldown,
                  reject_ingestor=reject_ingestor,
                  first_crawl_budget=config.first_crawl_budget,
                  passive_workers=config.passive_workers,
                  relevance_gate=relevance_gate)
