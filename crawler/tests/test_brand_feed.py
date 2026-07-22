from crawler.discovery.brand_feed import BRAND_SEEDS, BrandDomainCache
from crawler.discovery.query_grid import BRANDS


def test_brand_seeds_cover_exactly_the_brand_set():
    assert set(BRAND_SEEDS) == set(BRANDS)


def test_brand_seeds_have_bare_nonempty_fallback_domains():
    for brand, (qid, domain) in BRAND_SEEDS.items():
        assert domain and domain.strip(), brand
        assert " " not in domain and "/" not in domain, brand   # bare host, no scheme/path
        assert qid is None or qid.startswith("Q"), brand


def test_cache_defaults_empty_and_stale(tmp_path):
    c = BrandDomainCache.load(str(tmp_path / "b.json"))
    assert c.domains() == {}
    assert c.is_stale(3600) is True


def test_cache_replace_persists_and_reloads(tmp_path):
    path = str(tmp_path / "b.json")
    BrandDomainCache.load(path, clock=lambda: 1000.0).replace({"OKKO": "okko.ua"})
    assert BrandDomainCache.load(path).domains() == {"OKKO": "okko.ua"}


def test_cache_freshness_gate(tmp_path):
    now = {"t": 1000.0}
    c = BrandDomainCache.load(str(tmp_path / "b.json"), clock=lambda: now["t"])
    c.replace({"OKKO": "okko.ua"})
    assert c.is_stale(3600) is False        # just refreshed
    now["t"] = 1000.0 + 3600
    assert c.is_stale(3600) is True         # ttl elapsed


def test_cache_tolerates_corrupt_file(tmp_path):
    path = tmp_path / "b.json"
    path.write_text("{ not json", encoding="utf-8")
    assert BrandDomainCache.load(str(path)).domains() == {}


from crawler.discovery.brand_feed import BrandResolver, _host


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, get_payload=None, post_payload=None):
        self._get, self._post = get_payload, post_payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        return _FakeResp(self._get)

    def post(self, url, data=None):
        return _FakeResp(self._post)


def _resolver(get=None, post=None):
    return BrandResolver(client_factory=lambda: _FakeClient(get, post),
                         sleep=lambda s: None)


def test_host_normalizes_scheme_www_port_path():
    assert _host("https://www.Rozetka.com.ua/some/path") == "rozetka.com.ua"
    assert _host("okko.ua") == "okko.ua"
    assert _host("http://eva.ua:8080") == "eva.ua"
    assert _host("") is None


def test_resolve_uses_wikidata_p856_when_qid_present():
    payload = {"claims": {"P856": [
        {"mainsnak": {"datavalue": {"value": "https://okko.ua/"}}}]}}
    assert _resolver(get=payload).resolve("OKKO", "Q123") == "okko.ua"


def test_resolve_falls_back_to_overpass_website_aggregate():
    post = {"elements": [
        {"tags": {"website": "https://www.eva.ua/uk/"}},
        {"tags": {"contact:website": "http://eva.ua"}},
        {"tags": {"website": "https://other.example"}}]}
    assert _resolver(post=post).resolve("EVA", None) == "eva.ua"


def test_resolve_uses_overpass_brand_wikidata_then_p856():
    post = {"elements": [{"tags": {"brand:wikidata": "Q42"}}]}
    get = {"claims": {"P856": [
        {"mainsnak": {"datavalue": {"value": "https://wog.ua"}}}]}}
    assert _resolver(get=get, post=post).resolve("WOG", None) == "wog.ua"


def test_resolve_returns_none_on_failure():
    class _Boom:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise RuntimeError("net down")

        def post(self, *a, **k):
            raise RuntimeError("net down")

    r = BrandResolver(client_factory=lambda: _Boom(), sleep=lambda s: None)
    assert r.resolve("X", "Q1") is None
