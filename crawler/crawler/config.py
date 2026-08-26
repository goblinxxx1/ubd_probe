from dataclasses import dataclass, field

from pydantic_settings import BaseSettings, SettingsConfigDict

from crawler.models import BotCredential


class _RawSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    internal_api_url: str = "http://localhost:8000"
    crawler_api_key: str = "change-me-crawler-key"
    extractor: str = "heuristic"
    active_discovery: bool = False
    request_timeout: float = 20.0
    min_delay_seconds: float = 2.0
    instagram_accounts: str = ""
    facebook_accounts: str = ""
    proxies: str = ""
    search_providers: str = "duckduckgo,searxng"
    search_keywords: str = ""
    search_results_per_keyword: int = 7
    search_min_delay: float = 45.0
    search_backends: str = "startpage,duckduckgo,yahoo,brave,mojeek"
    search_state_path: str = "/data/search_state.json"
    search_cache_ttl_hours: int = 168
    search_jitter: float = 0.5
    search_backend_cooldown_base_seconds: float = 300.0
    search_backend_cooldown_cap_seconds: float = 21600.0
    search_global_backoff_hours: float = 6.0
    search_backend_quarantine_threshold: int = 6
    search_backend_quarantine_hours: float = 24.0
    search_backend_reprobe_hours: float = 6.0
    search_backoff_floor_seconds: float = 300.0
    search_budget: int = 0  # 0 = process all keywords
    active_fetch_budget: int = 80
    active_workers: int = 4
    first_crawl_budget: int = 10
    search_block_size: int = 15
    active_search_page_cap: int = 3   # Track 3: max SERP depth per phrase (two-dry rule trims earlier)
    grid_cities_enabled: bool = True
    site_query_enabled: bool = True
    site_query_budget: int = 5
    freshness_ttl_days: int = 30
    passive_interval_seconds: int = 172800   # 48h default; passive source-crawl cadence
    passive_workers: int = 4
    passive_state_path: str = "/data/passive_state.json"
    active_revisit_cooldown_days: int = 21
    brand_feed_enabled: bool = True
    brand_feed_refresh_hours: int = 336
    brand_domains_path: str = "/data/brand_domains.json"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    wikidata_url: str = "https://www.wikidata.org/w/api.php"
    brand_feed_per_pass: int = 20
    osm_feed_enabled: bool = True
    osm_feed_refresh_hours: int = 336
    osm_feed_per_pass: int = 20
    osm_domains_path: str = "/data/osm_domains.json"
    osm_feed_max_domains: int = 1500
    osm_min_pois: int = 1
    osm_feed_query_timeout: float = 200.0
    aggregator_feed_enabled: bool = True
    aggregator_feed_per_pass: int = 20
    aggregator_domains_path: str = "/data/aggregator_domains.json"
    aggregator_max_domains: int = 500
    sitemap_depth_enabled: bool = True
    domain_page_cap: int = 15
    sitemap_max_docs: int = 20
    bfs_max_depth: int = 2
    bfs_max_pages: int = 8
    bfs_trigger_min: int = 3
    domain_min_delay_seconds: float = 3.0
    crawl_delay_cap_seconds: float = 30.0
    robots_cache_path: str = "/data/robots_cache.json"
    robots_cache_ttl_hours: int = 168
    corpus_path: str = "/data/corpus.jsonl"
    corpus_max_mb: float = 50.0
    promo_lexicon_learned_path: str = "/data/promo_lexicon_learned.json"
    snowball_state_path: str = "/data/snowball_state.json"
    autofill_enabled: bool = False
    miner_min_domain_support: int = 3
    miner_min_logodds: float = 1.5
    miner_max_candidates_per_run: int = 50
    candidates_path: str = "/data/candidates.json"
    stoplist_path: str = "/data/stoplist.json"
    query_lexicon_enabled: bool = True
    query_lexicon_learned_path: str = "/data/query_lexicon_learned.json"
    query_candidates_path: str = "/data/query_candidates.json"
    query_stoplist_path: str = "/data/query_stoplist.json"
    query_lexicon_max_terms: int = 0   # miner grid-feed cap; 0 = unlimited (bounded by audit quality). Seed/categories never capped.
    query_lexicon_resurface_factor: float = 2.0
    query_miner_min_domain_support: int = 1   # v2: floor→1 surfaces single-host category terms at once
    query_miner_min_logodds: float = 0.9      # legacy; v2 query miner no longer gates on z (degenerate on all-pass corpus)
    query_miner_min_pass_docs: int = 2        # v2: anti-typo hapax guard on raw PASS-doc frequency
    query_miner_max_candidates_per_run: int = 0   # v2: 0 = unlimited ("все зразу"); safety ceiling applied in run_query_miner
    query_breed_promote_min: int = 2   # Задача 5B: поріг нових кандидатів/фразу для reward-breeding
    domain_rating_enabled: bool = True
    domain_registry_path: str = "/data/domain_registry.json"
    domain_feed_per_pass: int = 8
    domain_score_decay: float = 0.9
    domain_offer_weight: float = 1.0
    domain_error_weight: float = 0.5
    domain_promote_min_score: float = 0.5
    domain_evict_min_score: float = 0.1
    domain_evict_ttl_hours: int = 720
    rejection_feedback_enabled: bool = True
    domain_reject_weight: float = 1.0
    domain_empty_skip_crawls: int = 5
    reject_since_state_path: str = "/data/reject_since.json"
    geo_blocked_hosts_path: str = "/data/geo_blocked_hosts.json"
    lang_gate_enabled: bool = True
    editorial_gate_enabled: bool = True
    source_hint_enabled: bool = True
    lang_blocked_hosts_path: str = "/data/lang_blocked_hosts.json"
    attribution_hardening_enabled: bool = True
    blocked_hosts_fetch_enabled: bool = True
    aggregator_min_outbound: int = 3
    host_miner_min_support: int = 3
    host_miner_media_min: float = 0.5
    media_autoblock_enabled: bool = True
    media_autoblock_crawls: int = 2
    host_miner_aggregator_min: float = 0.5
    host_miner_max_candidates: int = 50
    require_discount: bool = True
    active_loop_delay_seconds: float = 60.0
    backoff_max_sleep_seconds: float = 1800.0
    passive_hard_overdue_factor: float = 3.0
    learn_interval_seconds: int = 86400   # 24h; in-loop self-learning tick (0 = off)
    query_terms_refresh_interval_seconds: int = 21600   # 6h; pull moderator-approved terms → grid
    searxng_url: str = "http://searxng:8080"
    searxng_engines: str = "google,bing,duckduckgo,brave,mojeek,qwant,marginalia,wikidata"  # NO yandex (project rule); google/bing verified live-working from our residential IP
    searxng_min_delay: float = 4.0
    judge_enabled: bool = True
    judge_url: str = "http://llama:8080"
    judge_model: str = "qwen2.5-7b-instruct"
    judge_timeout_seconds: float = 30.0
    judge_cache_path: str = "/data/judge_cache.json"


@dataclass
class Config:
    internal_api_url: str
    crawler_api_key: str
    extractor: str
    active_discovery: bool
    request_timeout: float
    min_delay_seconds: float
    bot_accounts: list[BotCredential] = field(default_factory=list)
    proxies: dict[str, str] = field(default_factory=dict)
    search_providers: list[str] = field(default_factory=list)
    search_keywords: list[str] = field(default_factory=list)
    search_results_per_keyword: int = 7
    search_min_delay: float = 45.0
    search_backends: list[str] = field(default_factory=list)
    search_state_path: str = "/data/search_state.json"
    search_cache_ttl_hours: int = 168
    search_jitter: float = 0.5
    search_backend_cooldown_base_seconds: float = 300.0
    search_backend_cooldown_cap_seconds: float = 21600.0
    search_global_backoff_hours: float = 6.0
    search_backend_quarantine_threshold: int = 6
    search_backend_quarantine_hours: float = 24.0
    search_backend_reprobe_hours: float = 6.0
    search_backoff_floor_seconds: float = 300.0
    search_budget: int | None = None
    active_fetch_budget: int = 80
    active_workers: int = 4
    first_crawl_budget: int = 10
    search_block_size: int = 15
    active_search_page_cap: int = 3   # Track 3: max SERP depth per phrase (two-dry rule trims earlier)
    grid_cities_enabled: bool = True
    site_query_enabled: bool = True
    site_query_budget: int = 5
    freshness_ttl_days: int = 30
    passive_interval_seconds: int = 172800   # 48h default; passive source-crawl cadence
    passive_workers: int = 4
    passive_state_path: str = "/data/passive_state.json"
    active_revisit_cooldown_days: int = 21
    brand_feed_enabled: bool = True
    brand_feed_refresh_hours: int = 336
    brand_domains_path: str = "/data/brand_domains.json"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    wikidata_url: str = "https://www.wikidata.org/w/api.php"
    brand_feed_per_pass: int = 20
    osm_feed_enabled: bool = True
    osm_feed_refresh_hours: int = 336
    osm_feed_per_pass: int = 20
    osm_domains_path: str = "/data/osm_domains.json"
    osm_feed_max_domains: int = 1500
    osm_min_pois: int = 1
    osm_feed_query_timeout: float = 200.0
    aggregator_feed_enabled: bool = True
    aggregator_feed_per_pass: int = 20
    aggregator_domains_path: str = "/data/aggregator_domains.json"
    aggregator_max_domains: int = 500
    sitemap_depth_enabled: bool = True
    domain_page_cap: int = 15
    sitemap_max_docs: int = 20
    bfs_max_depth: int = 2
    bfs_max_pages: int = 8
    bfs_trigger_min: int = 3
    domain_min_delay_seconds: float = 3.0
    crawl_delay_cap_seconds: float = 30.0
    robots_cache_path: str = "/data/robots_cache.json"
    robots_cache_ttl_hours: int = 168
    corpus_path: str = "/data/corpus.jsonl"
    corpus_max_mb: float = 50.0
    promo_lexicon_learned_path: str = "/data/promo_lexicon_learned.json"
    snowball_state_path: str = "/data/snowball_state.json"
    autofill_enabled: bool = False
    miner_min_domain_support: int = 3
    miner_min_logodds: float = 1.5
    miner_max_candidates_per_run: int = 50
    candidates_path: str = "/data/candidates.json"
    stoplist_path: str = "/data/stoplist.json"
    query_lexicon_enabled: bool = True
    query_lexicon_learned_path: str = "/data/query_lexicon_learned.json"
    query_candidates_path: str = "/data/query_candidates.json"
    query_stoplist_path: str = "/data/query_stoplist.json"
    query_lexicon_max_terms: int = 0   # miner grid-feed cap; 0 = unlimited (bounded by audit quality). Seed/categories never capped.
    query_lexicon_resurface_factor: float = 2.0
    query_miner_min_domain_support: int = 1   # v2: floor→1 surfaces single-host category terms at once
    query_miner_min_logodds: float = 0.9      # legacy; v2 query miner no longer gates on z (degenerate on all-pass corpus)
    query_miner_min_pass_docs: int = 2        # v2: anti-typo hapax guard on raw PASS-doc frequency
    query_miner_max_candidates_per_run: int = 0   # v2: 0 = unlimited ("все зразу"); safety ceiling applied in run_query_miner
    query_breed_promote_min: int = 2   # Задача 5B: поріг нових кандидатів/фразу для reward-breeding
    domain_rating_enabled: bool = True
    domain_registry_path: str = "/data/domain_registry.json"
    domain_feed_per_pass: int = 8
    domain_score_decay: float = 0.9
    domain_offer_weight: float = 1.0
    domain_error_weight: float = 0.5
    domain_promote_min_score: float = 0.5
    domain_evict_min_score: float = 0.1
    domain_evict_ttl_hours: int = 720
    rejection_feedback_enabled: bool = True
    domain_reject_weight: float = 1.0
    domain_empty_skip_crawls: int = 5
    reject_since_state_path: str = "/data/reject_since.json"
    geo_blocked_hosts_path: str = "/data/geo_blocked_hosts.json"
    lang_gate_enabled: bool = True
    editorial_gate_enabled: bool = True
    source_hint_enabled: bool = True
    lang_blocked_hosts_path: str = "/data/lang_blocked_hosts.json"
    attribution_hardening_enabled: bool = True
    blocked_hosts_fetch_enabled: bool = True
    aggregator_min_outbound: int = 3
    host_miner_min_support: int = 3
    host_miner_media_min: float = 0.5
    media_autoblock_enabled: bool = True
    media_autoblock_crawls: int = 2
    host_miner_aggregator_min: float = 0.5
    host_miner_max_candidates: int = 50
    require_discount: bool = True
    active_loop_delay_seconds: float = 60.0
    backoff_max_sleep_seconds: float = 1800.0
    passive_hard_overdue_factor: float = 3.0
    learn_interval_seconds: int = 86400   # 24h; in-loop self-learning tick (0 = off)
    query_terms_refresh_interval_seconds: int = 21600   # 6h; pull moderator-approved terms → grid
    searxng_url: str = "http://searxng:8080"
    searxng_engines: str = "google,bing,duckduckgo,brave,mojeek,qwant,marginalia,wikidata"
    searxng_min_delay: float = 4.0
    judge_enabled: bool = True
    judge_url: str = "http://llama:8080"
    judge_model: str = "qwen2.5-7b-instruct"
    judge_timeout_seconds: float = 30.0
    judge_cache_path: str = "/data/judge_cache.json"


def _parse_accounts(platform: str, raw: str) -> list[BotCredential]:
    out = []
    for chunk in (c.strip() for c in raw.split(",") if c.strip()):
        username, _, password = chunk.partition(":")
        out.append(BotCredential(platform=platform, username=username, password=password))
    return out


def _split_csv(raw: str) -> list[str]:
    return [c.strip() for c in raw.split(",") if c.strip()]


def _parse_proxies(raw: str) -> dict[str, str]:
    out = {}
    for chunk in (c.strip() for c in raw.split(",") if c.strip()):
        key, _, val = chunk.partition("=")
        out[key.strip()] = val.strip()
    return out


def from_settings(s: _RawSettings) -> Config:
    accounts = (_parse_accounts("instagram", s.instagram_accounts)
                + _parse_accounts("facebook", s.facebook_accounts))
    return Config(
        internal_api_url=s.internal_api_url,
        crawler_api_key=s.crawler_api_key,
        extractor=s.extractor,
        active_discovery=s.active_discovery,
        request_timeout=s.request_timeout,
        min_delay_seconds=s.min_delay_seconds,
        bot_accounts=accounts,
        proxies=_parse_proxies(s.proxies),
        search_providers=_split_csv(s.search_providers),
        search_keywords=_split_csv(s.search_keywords),
        search_results_per_keyword=s.search_results_per_keyword,
        search_min_delay=s.search_min_delay,
        search_backends=_split_csv(s.search_backends),
        search_state_path=s.search_state_path,
        search_cache_ttl_hours=s.search_cache_ttl_hours,
        search_jitter=s.search_jitter,
        search_backend_cooldown_base_seconds=s.search_backend_cooldown_base_seconds,
        search_backend_cooldown_cap_seconds=s.search_backend_cooldown_cap_seconds,
        search_global_backoff_hours=s.search_global_backoff_hours,
        search_backend_quarantine_threshold=s.search_backend_quarantine_threshold,
        search_backend_quarantine_hours=s.search_backend_quarantine_hours,
        search_backend_reprobe_hours=s.search_backend_reprobe_hours,
        search_backoff_floor_seconds=s.search_backoff_floor_seconds,
        search_budget=(s.search_budget or None),
        active_fetch_budget=s.active_fetch_budget,
        active_workers=s.active_workers,
        first_crawl_budget=s.first_crawl_budget,
        search_block_size=s.search_block_size,
        active_search_page_cap=s.active_search_page_cap,
        grid_cities_enabled=s.grid_cities_enabled,
        site_query_enabled=s.site_query_enabled,
        site_query_budget=s.site_query_budget,
        freshness_ttl_days=s.freshness_ttl_days,
        passive_interval_seconds=s.passive_interval_seconds,
        passive_workers=s.passive_workers,
        passive_state_path=s.passive_state_path,
        active_revisit_cooldown_days=s.active_revisit_cooldown_days,
        brand_feed_enabled=s.brand_feed_enabled,
        brand_feed_refresh_hours=s.brand_feed_refresh_hours,
        brand_domains_path=s.brand_domains_path,
        overpass_url=s.overpass_url,
        wikidata_url=s.wikidata_url,
        brand_feed_per_pass=s.brand_feed_per_pass,
        osm_feed_enabled=s.osm_feed_enabled,
        osm_feed_refresh_hours=s.osm_feed_refresh_hours,
        osm_feed_per_pass=s.osm_feed_per_pass,
        osm_domains_path=s.osm_domains_path,
        osm_feed_max_domains=s.osm_feed_max_domains,
        osm_min_pois=s.osm_min_pois,
        osm_feed_query_timeout=s.osm_feed_query_timeout,
        aggregator_feed_enabled=s.aggregator_feed_enabled,
        aggregator_feed_per_pass=s.aggregator_feed_per_pass,
        aggregator_domains_path=s.aggregator_domains_path,
        aggregator_max_domains=s.aggregator_max_domains,
        sitemap_depth_enabled=s.sitemap_depth_enabled,
        domain_page_cap=s.domain_page_cap,
        sitemap_max_docs=s.sitemap_max_docs,
        bfs_max_depth=s.bfs_max_depth,
        bfs_max_pages=s.bfs_max_pages,
        bfs_trigger_min=s.bfs_trigger_min,
        domain_min_delay_seconds=s.domain_min_delay_seconds,
        crawl_delay_cap_seconds=s.crawl_delay_cap_seconds,
        robots_cache_path=s.robots_cache_path,
        robots_cache_ttl_hours=s.robots_cache_ttl_hours,
        corpus_path=s.corpus_path,
        corpus_max_mb=s.corpus_max_mb,
        promo_lexicon_learned_path=s.promo_lexicon_learned_path,
        snowball_state_path=s.snowball_state_path,
        autofill_enabled=s.autofill_enabled,
        miner_min_domain_support=s.miner_min_domain_support,
        miner_min_logodds=s.miner_min_logodds,
        miner_max_candidates_per_run=s.miner_max_candidates_per_run,
        candidates_path=s.candidates_path,
        stoplist_path=s.stoplist_path,
        query_lexicon_enabled=s.query_lexicon_enabled,
        query_lexicon_learned_path=s.query_lexicon_learned_path,
        query_candidates_path=s.query_candidates_path,
        query_stoplist_path=s.query_stoplist_path,
        query_lexicon_max_terms=s.query_lexicon_max_terms,
        query_lexicon_resurface_factor=s.query_lexicon_resurface_factor,
        query_miner_min_domain_support=s.query_miner_min_domain_support,
        query_miner_min_logodds=s.query_miner_min_logodds,
        query_miner_min_pass_docs=s.query_miner_min_pass_docs,
        query_breed_promote_min=s.query_breed_promote_min,
        query_miner_max_candidates_per_run=s.query_miner_max_candidates_per_run,
        domain_rating_enabled=s.domain_rating_enabled,
        domain_registry_path=s.domain_registry_path,
        domain_feed_per_pass=s.domain_feed_per_pass,
        domain_score_decay=s.domain_score_decay,
        domain_offer_weight=s.domain_offer_weight,
        domain_error_weight=s.domain_error_weight,
        domain_promote_min_score=s.domain_promote_min_score,
        domain_evict_min_score=s.domain_evict_min_score,
        domain_evict_ttl_hours=s.domain_evict_ttl_hours,
        rejection_feedback_enabled=s.rejection_feedback_enabled,
        domain_reject_weight=s.domain_reject_weight,
        domain_empty_skip_crawls=s.domain_empty_skip_crawls,
        reject_since_state_path=s.reject_since_state_path,
        geo_blocked_hosts_path=s.geo_blocked_hosts_path,
        lang_gate_enabled=s.lang_gate_enabled,
        editorial_gate_enabled=s.editorial_gate_enabled,
        source_hint_enabled=s.source_hint_enabled,
        lang_blocked_hosts_path=s.lang_blocked_hosts_path,
        attribution_hardening_enabled=s.attribution_hardening_enabled,
        blocked_hosts_fetch_enabled=s.blocked_hosts_fetch_enabled,
        aggregator_min_outbound=s.aggregator_min_outbound,
        host_miner_min_support=s.host_miner_min_support,
        host_miner_media_min=s.host_miner_media_min,
        media_autoblock_enabled=s.media_autoblock_enabled,
        media_autoblock_crawls=s.media_autoblock_crawls,
        host_miner_aggregator_min=s.host_miner_aggregator_min,
        host_miner_max_candidates=s.host_miner_max_candidates,
        require_discount=s.require_discount,
        active_loop_delay_seconds=s.active_loop_delay_seconds,
        backoff_max_sleep_seconds=s.backoff_max_sleep_seconds,
        passive_hard_overdue_factor=s.passive_hard_overdue_factor,
        learn_interval_seconds=s.learn_interval_seconds,
        query_terms_refresh_interval_seconds=s.query_terms_refresh_interval_seconds,
        searxng_url=s.searxng_url,
        searxng_engines=s.searxng_engines,
        searxng_min_delay=s.searxng_min_delay,
        judge_enabled=s.judge_enabled,
        judge_url=s.judge_url,
        judge_model=s.judge_model,
        judge_timeout_seconds=s.judge_timeout_seconds,
        judge_cache_path=s.judge_cache_path,
    )


def load_config() -> Config:
    return from_settings(_RawSettings())
