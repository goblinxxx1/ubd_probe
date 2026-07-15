from types import SimpleNamespace
from crawler.discovery.providers import build_search_provider


def _cfg(**over):
    base = dict(search_providers=["duckduckgo"], search_results_per_keyword=3,
                search_min_delay=0)
    base.update(over)
    return SimpleNamespace(**base)


def test_build_returns_callable_for_known_provider():
    p = build_search_provider(_cfg())
    assert callable(p)


def test_build_returns_none_when_no_known_providers():
    assert build_search_provider(_cfg(search_providers=[])) is None
    assert build_search_provider(_cfg(search_providers=["unknown"])) is None
