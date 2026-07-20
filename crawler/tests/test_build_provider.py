from types import SimpleNamespace

from crawler.discovery.providers import build_search_provider


def _cfg(tmp_path, **over):
    base = dict(
        search_providers=["duckduckgo"], search_results_per_keyword=3, search_min_delay=0,
        search_backends=["google", "brave"], search_state_path=str(tmp_path / "state.json"),
        search_cache_ttl_hours=168, search_jitter=0.5,
        search_backend_cooldown_base_seconds=300.0, search_backend_cooldown_cap_seconds=21600.0,
        search_global_backoff_hours=6.0, searxng_url="http://searxng:8080",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_build_returns_callable_for_known_provider(tmp_path):
    p = build_search_provider(_cfg(tmp_path))
    assert callable(p)


def test_build_returns_none_when_no_known_providers(tmp_path):
    assert build_search_provider(_cfg(tmp_path, search_providers=[])) is None
    assert build_search_provider(_cfg(tmp_path, search_providers=["unknown"])) is None
