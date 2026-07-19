from crawler.discovery.providers import DuckDuckGoProvider, _normalize_url


class FakeDDGS:
    def __init__(self, results): self._results = results
    def text(self, query, max_results=7, **kwargs):
        return self._results


class CapturingDDGS:
    def __init__(self): self.kwargs = None
    def text(self, query, **kwargs):
        self.kwargs = kwargs
        return []


def _provider(results):
    return DuckDuckGoProvider(results_per_keyword=3, min_delay=0,
                              ddgs_factory=lambda: FakeDDGS(results),
                              sleep=lambda _s: None)


def test_normalize_url_strips_utm_fragment_trailing_and_lowercases_host():
    assert _normalize_url("HTTPS://Shop.Example.com/deal/?utm_source=x#frag") \
        == "https://shop.example.com/deal"
    assert _normalize_url("https://ex.com/") == "https://ex.com"


def test_normalize_url_rejects_junk():
    assert _normalize_url("not a url") is None
    assert _normalize_url("") is None


def test_provider_maps_results_to_website_candidates():
    p = _provider([
        {"title": "Кафе знижки", "href": "https://cafe.example/veterans?utm_medium=x", "body": "b"},
        {"title": "Shop", "href": "https://shop.example/", "body": "b"},
    ])
    cands = p("знижки ветеранам")
    assert [c.url_or_handle for c in cands] == \
        ["https://cafe.example/veterans", "https://shop.example"]
    assert all(c.type == "website" for c in cands)
    assert cands[0].discovery_note == "ddg: знижки ветеранам"
    assert cands[0].name == "Кафе знижки"


def test_provider_excludes_yandex_backend():
    # yandex reliably times out from Docker/CI IPs, stalling every query ~5s.
    fake = CapturingDDGS()
    p = DuckDuckGoProvider(min_delay=0, ddgs_factory=lambda: fake, sleep=lambda _s: None)
    p("kw")
    backend = fake.kwargs.get("backend", "")
    assert "yandex" not in backend
    assert "duckduckgo" in backend      # still queries real engines, just not yandex


def test_provider_is_best_effort_on_error():
    class Boom:
        def text(self, *a, **k): raise RuntimeError("banned")
    p = DuckDuckGoProvider(ddgs_factory=lambda: Boom(), min_delay=0, sleep=lambda _s: None)
    assert p("kw") == []
