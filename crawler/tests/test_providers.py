from crawler.discovery.providers import RotatingDdgProvider, _normalize_url
from crawler.discovery.search_state import SearchState

POOL = ["google", "startpage", "duckduckgo", "yahoo", "brave"]


class FakeDDGS:
    def __init__(self, results):
        self._results = results

    def text(self, query, max_results=7, **kwargs):
        return self._results


class CapturingDDGS:
    def __init__(self):
        self.kwargs = None

    def text(self, query, **kwargs):
        self.kwargs = kwargs
        return []


def _provider(tmp_path, factory):
    st = SearchState(str(tmp_path / "state.json"), clock=lambda: 1000.0)
    return RotatingDdgProvider(pool=POOL, state=st, results_per_keyword=3, min_delay=0,
                               jitter=0.0, ddgs_factory=factory, sleep=lambda _s: None,
                               rand=lambda: 0.0)


def test_normalize_url_strips_utm_fragment_trailing_and_lowercases_host():
    assert _normalize_url("HTTPS://Shop.Example.com/deal/?utm_source=x#frag") \
        == "https://shop.example.com/deal"
    assert _normalize_url("https://ex.com/") == "https://ex.com"


def test_normalize_url_rejects_junk():
    assert _normalize_url("not a url") is None
    assert _normalize_url("") is None


def test_provider_maps_results_to_website_candidates(tmp_path):
    p = _provider(tmp_path, lambda: FakeDDGS([
        {"title": "Кафе знижки", "href": "https://cafe.example/veterans?utm_medium=x", "body": "b"},
        {"title": "Shop", "href": "https://shop.example/", "body": "b"},
    ]))
    cands = p("знижки ветеранам")
    assert [c.url_or_handle for c in cands] == \
        ["https://cafe.example/veterans", "https://shop.example"]
    assert all(c.type == "website" for c in cands)
    assert cands[0].discovery_note == "ddg:google: знижки ветеранам"
    assert cands[0].name == "Кафе знижки"


def test_provider_queries_single_backend_from_pool(tmp_path):
    fake = CapturingDDGS()
    p = _provider(tmp_path, lambda: fake)
    p("kw")
    assert fake.kwargs.get("backend") in POOL
    assert "," not in fake.kwargs.get("backend")     # one endpoint, not the whole list


def test_provider_is_best_effort_on_error(tmp_path):
    class Boom:
        def text(self, *a, **k):
            raise RuntimeError("banned")
    p = _provider(tmp_path, lambda: Boom())
    assert p("kw") == []
