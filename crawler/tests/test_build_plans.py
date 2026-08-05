from types import SimpleNamespace

from crawler.discovery.providers import build_search_plans


def _cfg(tmp_path, **over):
    base = dict(
        search_providers=["duckduckgo"], search_results_per_keyword=3, search_min_delay=0,
        search_backends=["google", "brave"], search_state_path=str(tmp_path / "state.json"),
        search_cache_ttl_hours=168, search_jitter=0.5,
        search_backend_cooldown_base_seconds=300.0, search_backend_cooldown_cap_seconds=21600.0,
        search_global_backoff_hours=6.0, search_budget=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_ddg_only_plan(tmp_path):
    plans = build_search_plans(_cfg(tmp_path))
    assert [p.name for p in plans] == ["duckduckgo"]
    assert plans[0].include_pins is True


def test_no_known_providers_yields_empty(tmp_path):
    assert build_search_plans(_cfg(tmp_path, search_providers=[])) == []
    assert build_search_plans(_cfg(tmp_path, search_providers=["nope"])) == []
