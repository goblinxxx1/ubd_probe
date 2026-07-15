import httpx
from types import SimpleNamespace

from crawler.discovery.providers import SearxngProvider, build_search_provider


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


def test_build_provider_supports_searxng():
    cfg = SimpleNamespace(search_providers=["searxng"], search_results_per_keyword=3,
                          search_min_delay=0, searxng_url="http://searxng:8080")
    assert callable(build_search_provider(cfg))
