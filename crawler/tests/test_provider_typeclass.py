import httpx

from crawler.discovery.providers import RotatingDdgProvider, SearxngProvider
from crawler.discovery.search_state import SearchState


class FakeDDGS:
    def __init__(self, results):
        self._results = results

    def text(self, query, max_results=7, **kwargs):
        return self._results


def test_ddg_provider_classifies_and_skips_junk(tmp_path):
    results = [
        {"title": "Site", "href": "https://shop.example/deal", "body": "b"},
        {"title": "TG", "href": "https://t.me/veteranychat", "body": "b"},
        {"title": "IG post", "href": "https://instagram.com/p/AbC", "body": "b"},
        {"title": "IG prof", "href": "https://instagram.com/veteranshop", "body": "b"},
    ]
    st = SearchState(str(tmp_path / "state.json"), clock=lambda: 1000.0)
    p = RotatingDdgProvider(pool=["google"], state=st, results_per_keyword=10, min_delay=0,
                            jitter=0.0, ddgs_factory=lambda: FakeDDGS(results),
                            sleep=lambda _s: None, rand=lambda: 0.0)
    cands = p("kw")
    got = {(c.type, c.url_or_handle) for c in cands}
    assert ("website", "https://shop.example/deal") in got
    assert ("telegram", "https://t.me/veteranychat") in got
    assert ("instagram", "https://instagram.com/veteranshop") in got
    assert all("instagram.com/p/" not in c.url_or_handle for c in cands)
    assert len(cands) == 3


def _searx_factory(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_searxng_provider_classifies_and_skips_junk():
    def handler(req):
        return httpx.Response(200, json={"results": [
            {"url": "https://shop.example/deal", "title": "Site"},
            {"url": "https://t.me/vetchan", "title": "TG"},
            {"url": "https://facebook.com/share/x", "title": "FB share"},
        ]})
    p = SearxngProvider("http://searxng:8080", results_per_keyword=10, min_delay=0,
                        client_factory=_searx_factory(handler), sleep=lambda _s: None)
    cands = p("kw")
    got = {(c.type, c.url_or_handle) for c in cands}
    assert ("website", "https://shop.example/deal") in got
    assert ("telegram", "https://t.me/vetchan") in got
    assert all("facebook.com/share" not in c.url_or_handle for c in cands)
    assert len(cands) == 2
