import os

from crawler.config import load_config


def test_load_config_parses_accounts_and_flags(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_URL", "http://api")
    monkeypatch.setenv("CRAWLER_API_KEY", "k")
    monkeypatch.setenv("ACTIVE_DISCOVERY", "true")
    monkeypatch.setenv("INSTAGRAM_ACCOUNTS", "bot_a:pw1,bot_b:pw2")
    monkeypatch.setenv("FACEBOOK_ACCOUNTS", "")
    monkeypatch.setenv("PROXIES", "instagram=http://p1")

    cfg = load_config()
    assert cfg.internal_api_url == "http://api"
    assert cfg.active_discovery is True
    assert cfg.extractor == "heuristic"
    igs = [b for b in cfg.bot_accounts if b.platform == "instagram"]
    assert [b.username for b in igs] == ["bot_a", "bot_b"]
    assert igs[0].password == "pw1"
    assert cfg.proxies["instagram"] == "http://p1"


def test_active_fetch_budget_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    assert load_config().active_fetch_budget == 80


def test_scheduler_config_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    c = load_config()
    assert c.active_loop_delay_seconds == 60.0
    assert c.backoff_max_sleep_seconds == 1800.0
    assert c.passive_hard_overdue_factor == 3.0


def test_search_antithrottle_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.search_backends == ["startpage", "duckduckgo", "yahoo", "brave", "mojeek"]
    assert cfg.search_state_path == "/data/search_state.json"
    assert cfg.search_cache_ttl_hours == 168
    assert cfg.search_min_delay == 45.0
    assert cfg.search_jitter == 0.5
    assert cfg.search_backend_cooldown_base_seconds == 300.0
    assert cfg.search_backend_cooldown_cap_seconds == 21600.0
    assert cfg.search_global_backoff_hours == 6.0


def test_search_backends_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_BACKENDS", "brave, mojeek")
    assert load_config().search_backends == ["brave", "mojeek"]


def test_freshness_ttl_days_default_and_override(monkeypatch):
    from crawler.config import load_config
    monkeypatch.delenv("FRESHNESS_TTL_DAYS", raising=False)
    assert load_config().freshness_ttl_days == 30
    monkeypatch.setenv("FRESHNESS_TTL_DAYS", "7")
    assert load_config().freshness_ttl_days == 7


def test_passive_schedule_defaults_and_override(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)   # no .env -> defaults apply
    monkeypatch.delenv("PASSIVE_INTERVAL_SECONDS", raising=False)
    cfg = load_config()
    assert cfg.passive_interval_seconds == 172800
    assert cfg.passive_state_path == "/data/passive_state.json"
    monkeypatch.setenv("PASSIVE_INTERVAL_SECONDS", "345600")
    assert load_config().passive_interval_seconds == 345600


def test_brand_feed_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.brand_feed_enabled is True
    assert cfg.brand_feed_refresh_hours == 336
    assert cfg.brand_domains_path == "/data/brand_domains.json"
    assert cfg.overpass_url == "https://overpass-api.de/api/interpreter"
    assert cfg.wikidata_url == "https://www.wikidata.org/w/api.php"


def test_brand_feed_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRAND_FEED_ENABLED", "false")
    monkeypatch.setenv("BRAND_FEED_REFRESH_HOURS", "48")
    cfg = load_config()
    assert cfg.brand_feed_enabled is False
    assert cfg.brand_feed_refresh_hours == 48


def test_brand_feed_per_pass_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert load_config().brand_feed_per_pass == 20


def test_brand_feed_per_pass_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRAND_FEED_PER_PASS", "5")
    assert load_config().brand_feed_per_pass == 5


def test_sitemap_depth_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.sitemap_depth_enabled is True
    assert cfg.domain_page_cap == 15
    assert cfg.sitemap_max_docs == 20
    assert cfg.bfs_max_depth == 2
    assert cfg.bfs_max_pages == 8
    assert cfg.bfs_trigger_min == 3
    assert cfg.domain_min_delay_seconds == 3.0
    assert cfg.crawl_delay_cap_seconds == 30.0
    assert cfg.robots_cache_path == "/data/robots_cache.json"
    assert cfg.robots_cache_ttl_hours == 168


def test_domain_rating_defaults():
    from crawler.config import _RawSettings
    s = _RawSettings()
    assert s.domain_rating_enabled is True
    assert s.domain_registry_path == "/data/domain_registry.json"
    assert s.domain_feed_per_pass == 8
    assert s.domain_score_decay == 0.9
    assert s.domain_offer_weight == 1.0
    assert s.domain_error_weight == 0.5
    assert s.domain_promote_min_score == 0.5
    assert s.domain_evict_min_score == 0.1
    assert s.domain_evict_ttl_hours == 720


def test_attribution_hardening_defaults():
    from crawler.config import _RawSettings
    s = _RawSettings()
    assert s.attribution_hardening_enabled is True
    assert s.blocked_hosts_fetch_enabled is True
    assert s.aggregator_min_outbound == 3
    assert s.host_miner_min_support == 3
    assert s.host_miner_media_min == 0.5
    assert s.host_miner_aggregator_min == 0.5
    assert s.host_miner_max_candidates == 50


def test_site_query_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.site_query_enabled is True
    assert cfg.site_query_budget == 5


def test_site_query_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SITE_QUERY_ENABLED", "false")
    monkeypatch.setenv("SITE_QUERY_BUDGET", "9")
    cfg = load_config()
    assert cfg.site_query_enabled is False
    assert cfg.site_query_budget == 9


def test_osm_feed_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.osm_feed_enabled is True
    assert cfg.osm_feed_refresh_hours == 336
    assert cfg.osm_feed_per_pass == 20
    assert cfg.osm_domains_path == "/data/osm_domains.json"
    assert cfg.osm_feed_max_domains == 1500
    assert cfg.osm_min_pois == 1


def test_osm_feed_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OSM_FEED_ENABLED", "false")
    monkeypatch.setenv("OSM_FEED_MAX_DOMAINS", "50")
    monkeypatch.setenv("OSM_MIN_POIS", "3")
    cfg = load_config()
    assert cfg.osm_feed_enabled is False
    assert cfg.osm_feed_max_domains == 50
    assert cfg.osm_min_pois == 3


def test_osm_feed_query_timeout_default_and_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert load_config().osm_feed_query_timeout == 200.0
    monkeypatch.setenv("OSM_FEED_QUERY_TIMEOUT", "150")
    assert load_config().osm_feed_query_timeout == 150.0


def test_aggregator_feed_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.aggregator_feed_enabled is True
    assert cfg.aggregator_feed_per_pass == 20
    assert cfg.aggregator_domains_path == "/data/aggregator_domains.json"
    assert cfg.aggregator_max_domains == 500


def test_aggregator_feed_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGGREGATOR_FEED_ENABLED", "false")
    monkeypatch.setenv("AGGREGATOR_MAX_DOMAINS", "50")
    cfg = load_config()
    assert cfg.aggregator_feed_enabled is False
    assert cfg.aggregator_max_domains == 50


def test_require_discount_default_true(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    assert load_config().require_discount is True


def test_require_discount_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REQUIRE_DISCOUNT", "false")
    assert load_config().require_discount is False


def test_grid_cities_raw_default_true():
    from crawler.config import _RawSettings
    s = _RawSettings()
    assert s.grid_cities_enabled is True


def test_grid_cities_config_dataclass_default_true():
    from crawler.config import Config
    cfg = Config(internal_api_url="x", crawler_api_key="k", extractor="heuristic",
                 active_discovery=False, request_timeout=1.0, min_delay_seconds=0.0)
    assert cfg.grid_cities_enabled is True


def test_load_config_passes_grid_cities(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> env overrides apply cleanly
    monkeypatch.setenv("GRID_CITIES_ENABLED", "false")
    cfg = load_config()
    assert cfg.grid_cities_enabled is False


def test_active_revisit_cooldown_default_and_override(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ACTIVE_REVISIT_COOLDOWN_DAYS", raising=False)
    assert load_config().active_revisit_cooldown_days == 21
    monkeypatch.setenv("ACTIVE_REVISIT_COOLDOWN_DAYS", "7")
    assert load_config().active_revisit_cooldown_days == 7


def test_search_block_size_default_and_override(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    assert load_config().search_block_size == 15
    monkeypatch.setenv("SEARCH_BLOCK_SIZE", "8")
    assert load_config().search_block_size == 8


def test_query_lexicon_defaults():
    from crawler.config import _RawSettings, Config
    assert _RawSettings().query_lexicon_enabled is True
    cfg = Config(internal_api_url="x", crawler_api_key="k", extractor="heuristic",
                 active_discovery=False, request_timeout=1.0, min_delay_seconds=0.0)
    assert cfg.query_lexicon_max_terms == 0   # 0 = miner grid-feed uncapped (bounded by audit quality)
    assert cfg.query_lexicon_resurface_factor == 2.0


def test_reject_feedback_defaults_and_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.rejection_feedback_enabled is True
    assert cfg.domain_reject_weight == 1.0
    assert cfg.reject_since_state_path == "/data/reject_since.json"
    monkeypatch.setenv("REJECTION_FEEDBACK_ENABLED", "false")
    monkeypatch.setenv("DOMAIN_REJECT_WEIGHT", "1.5")
    assert load_config().rejection_feedback_enabled is False
    assert load_config().domain_reject_weight == 1.5


def test_lang_gate_defaults_on(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)      # no .env -> env overrides apply cleanly
    monkeypatch.delenv("LANG_GATE_ENABLED", raising=False)
    cfg = load_config()
    assert cfg.lang_gate_enabled is True
    assert cfg.lang_blocked_hosts_path.endswith("lang_blocked_hosts.json")


def test_lang_gate_can_be_disabled(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANG_GATE_ENABLED", "false")
    assert load_config().lang_gate_enabled is False


def test_editorial_gate_defaults_on(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDITORIAL_GATE_ENABLED", raising=False)
    assert load_config().editorial_gate_enabled is True


def test_editorial_gate_can_be_disabled(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITORIAL_GATE_ENABLED", "false")
    assert load_config().editorial_gate_enabled is False


def test_source_hint_defaults_on(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOURCE_HINT_ENABLED", raising=False)
    assert load_config().source_hint_enabled is True


def test_query_miner_min_logodds_default_lowered():
    from crawler.config import _RawSettings, Config
    assert _RawSettings().query_miner_min_logodds == 0.9
    cfg = Config(internal_api_url="x", crawler_api_key="k", extractor="heuristic",
                 active_discovery=False, request_timeout=1.0, min_delay_seconds=0.0)
    assert cfg.query_miner_min_logodds == 0.9


def test_query_terms_refresh_interval_default():
    from crawler.config import _RawSettings, Config
    assert _RawSettings().query_terms_refresh_interval_seconds == 21600
    cfg = Config(internal_api_url="x", crawler_api_key="k", extractor="heuristic",
                 active_discovery=False, request_timeout=1.0, min_delay_seconds=0.0)
    assert cfg.query_terms_refresh_interval_seconds == 21600


def test_passive_workers_default_and_env(monkeypatch):
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.passive_workers == 4

    monkeypatch.setenv("PASSIVE_WORKERS", "8")
    cfg2 = load_config()
    assert cfg2.passive_workers == 8


def test_active_workers_default_and_env(monkeypatch):
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.active_workers == 4

    monkeypatch.setenv("ACTIVE_WORKERS", "6")
    cfg2 = load_config()
    assert cfg2.active_workers == 6


def test_judge_config_defaults(monkeypatch):
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.judge_enabled is True
    assert cfg.judge_model == "qwen2.5-7b-instruct"
    monkeypatch.setenv("JUDGE_ENABLED", "false")
    assert load_config().judge_enabled is False


def test_phrase_scheduler_tunables_have_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("CRAWLER_API_KEY", "k")
    monkeypatch.setenv("INTERNAL_API_URL", "http://x")
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.phrase_cold_tries == 3
    assert cfg.phrase_ttl_mult_cap == 8.0
    assert cfg.phrase_ewma_alpha == 0.3
