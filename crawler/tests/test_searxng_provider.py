import httpx
from types import SimpleNamespace

from crawler.discovery.providers import SearxngProvider, build_search_plans


def _factory(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_searxng_maps_results_to_website_candidates():
    def handler(req):
        assert req.url.path == "/search"
        assert req.url.params["format"] == "json"
        assert req.url.params["q"] == "kw"
        return httpx.Response(200, json={"results": [
            {"url": "https://a.example/x?utm_source=1", "title": "A"},
            {"url": "https://b.example/", "title": "B"},
        ]})
    p = SearxngProvider("http://searxng:8080/", results_per_keyword=5, min_delay=0,
                        client_factory=_factory(handler), sleep=lambda _s: None)
    cands = p("kw")
    assert [c.url_or_handle for c in cands] == ["https://a.example/x", "https://b.example"]
    assert cands[0].type == "website"
    assert cands[0].discovery_note == "searxng: kw"
    assert cands[0].name == "A"


def test_searxng_best_effort_on_http_error():
    def handler(req): return httpx.Response(500)
    p = SearxngProvider("http://searxng:8080", min_delay=0,
                        client_factory=_factory(handler), sleep=lambda _s: None)
    assert p("kw") == []


def test_build_plans_supports_searxng(tmp_path):
    cfg = SimpleNamespace(search_providers=["searxng"], search_results_per_keyword=3,
                          search_min_delay=0, searxng_url="http://searxng:8080",
                          search_state_path=str(tmp_path / "s.json"), search_budget=0)
    plans = build_search_plans(cfg)
    assert [p.name for p in plans] == ["searxng"]
    assert plans[0].cursor_key == "searxng_cursor"


def test_searxng_slice_ok_tracks_success_and_reset():
    def ok_handler(req):
        return httpx.Response(200, json={"results": [{"url": "https://a.example/", "title": "A"}]})
    p = SearxngProvider("http://searxng:8080", min_delay=0,
                        client_factory=_factory(ok_handler), sleep=lambda _s: None)
    assert p.slice_ok() is False        # fresh
    p("kw")
    assert p.slice_ok() is True         # a successful query happened
    p.reset_slice()
    assert p.slice_ok() is False        # reset for next slice


def test_searxng_slice_ok_stays_false_on_error():
    def err_handler(req): return httpx.Response(500)
    p = SearxngProvider("http://searxng:8080", min_delay=0,
                        client_factory=_factory(err_handler), sleep=lambda _s: None)
    p.reset_slice()
    p("kw")
    assert p.slice_ok() is False        # error must not mark the slice productive
