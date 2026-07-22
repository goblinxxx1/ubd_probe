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
    assert load_config().active_fetch_budget == 20


def test_search_antithrottle_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.search_backends == ["google", "startpage", "duckduckgo", "yahoo", "brave"]
    assert cfg.search_state_path == "/data/search_state.json"
    assert cfg.search_cache_ttl_hours == 168
    assert cfg.search_min_delay == 45.0
    assert cfg.search_jitter == 0.5
    assert cfg.search_backend_cooldown_base_seconds == 300.0
    assert cfg.search_backend_cooldown_cap_seconds == 21600.0
    assert cfg.search_global_backoff_hours == 6.0


def test_search_backends_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_BACKENDS", "google, brave")
    assert load_config().search_backends == ["google", "brave"]


def test_freshness_ttl_days_default_and_override(monkeypatch):
    from crawler.config import load_config
    monkeypatch.delenv("FRESHNESS_TTL_DAYS", raising=False)
    assert load_config().freshness_ttl_days == 30
    monkeypatch.setenv("FRESHNESS_TTL_DAYS", "7")
    assert load_config().freshness_ttl_days == 7


def test_search_queries_per_pass_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    assert load_config().search_queries_per_pass == 40


def test_search_queries_per_pass_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_QUERIES_PER_PASS", "12")
    assert load_config().search_queries_per_pass == 12


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
