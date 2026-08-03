from crawler.discovery.osm_feed import OsmEnumerator


class _FakeResp:
    def __init__(self, payload): self._payload = payload
    def raise_for_status(self): pass
    def json(self): return self._payload


class _FakeClient:
    def __init__(self, post_payload=None, boom=False):
        self._post, self._boom = post_payload, boom
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def post(self, url, data=None):
        if self._boom:
            raise RuntimeError("net down")
        return _FakeResp(self._post)


def _enum(elements, boom=False, **kw):
    return OsmEnumerator(
        overpass_url="http://ov", sleep=lambda s: None,
        client_factory=lambda: _FakeClient({"elements": elements}, boom=boom), **kw)


def test_aggregates_and_filters_by_min_pois():
    els = [{"tags": {"brand": "Foo", "website": "https://foo.ua/x"}},
           {"tags": {"brand": "Foo", "website": "http://foo.ua"}},
           {"tags": {"brand": "Bar", "website": "https://bar.ua"}}]   # single POI
    assert _enum(els, min_pois=2).enumerate() == {"Foo": "foo.ua"}


def test_contact_website_fallback():
    els = [{"tags": {"brand": "Cee", "contact:website": "https://cee.ua"}},
           {"tags": {"brand": "Cee", "contact:website": "https://cee.ua/uk"}}]
    assert _enum(els, min_pois=2).enumerate() == {"Cee": "cee.ua"}


def test_dedup_by_host_stable_first_brand_wins():
    els = [{"tags": {"brand": "Bbb", "website": "https://same.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://same.ua"}},
           {"tags": {"brand": "Aaa", "website": "https://same.ua"}},
           {"tags": {"brand": "Aaa", "website": "https://same.ua"}}]
    assert _enum(els, min_pois=2).enumerate() == {"Aaa": "same.ua"}


def test_cap_max_domains():
    els = [{"tags": {"brand": "Aaa", "website": "https://a.ua"}},
           {"tags": {"brand": "Aaa", "website": "https://a.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://b.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://b.ua"}}]
    assert _enum(els, min_pois=2, max_domains=1).enumerate() == {"Aaa": "a.ua"}


def test_blocklisted_host_filtered(monkeypatch):
    import crawler.discovery.osm_feed as m
    monkeypatch.setattr(m, "is_blocked_host", lambda h: h == "bad.ua")
    els = [{"tags": {"brand": "Good", "website": "https://good.ua"}},
           {"tags": {"brand": "Good", "website": "https://good.ua"}},
           {"tags": {"brand": "Bad", "website": "https://bad.ua"}},
           {"tags": {"brand": "Bad", "website": "https://bad.ua"}}]
    assert _enum(els, min_pois=2).enumerate() == {"Good": "good.ua"}


def test_foreign_cctld_website_filtered():
    # UA POI of a brand whose website is a .by domain (e.g. БРСМ -> brsm.by) must
    # not poison the domain cache
    els = [{"tags": {"brand": "БРСМ", "website": "https://brsm.by"}},
           {"tags": {"brand": "БРСМ", "website": "https://brsm.by"}},
           {"tags": {"brand": "Good", "website": "https://good.ua"}},
           {"tags": {"brand": "Good", "website": "https://good.ua"}}]
    assert _enum(els, min_pois=2).enumerate() == {"Good": "good.ua"}


def test_missing_brand_or_website_skipped():
    els = [{"tags": {"website": "https://x.ua"}},        # no brand
           {"tags": {"brand": "Y"}},                     # no website
           {"tags": {}}]
    assert _enum(els, min_pois=1).enumerate() == {}


def test_http_failure_returns_empty():
    assert _enum([], boom=True).enumerate() == {}


from crawler.discovery.brand_feed import BrandDomainCache
from crawler.discovery.osm_feed import OsmDomainFeed
from crawler.discovery.passive import normalize_ref


def _cache(tmp_path, mapping):
    c = BrandDomainCache.load(str(tmp_path / "osm.json"))
    c.replace(mapping)
    return c


def test_feed_emits_website_candidates(tmp_path):
    c = _cache(tmp_path, {"OKKO": "okko.ua", "EVA": "eva.ua"})
    cands = {x.name: x for x in OsmDomainFeed(c).candidates(known=set())}
    assert cands["OKKO"].type == "website"
    assert cands["OKKO"].url_or_handle == "https://okko.ua"
    assert cands["OKKO"].discovery_note == "osm-feed:okko.ua"


def test_feed_skips_known(tmp_path):
    c = _cache(tmp_path, {"OKKO": "okko.ua"})
    known = {normalize_ref("website", "https://okko.ua")}
    assert OsmDomainFeed(c).candidates(known) == []


def test_feed_empty_cache_is_safe(tmp_path):
    c = BrandDomainCache.load(str(tmp_path / "osm.json"))   # no replace → empty
    assert OsmDomainFeed(c).candidates(known=set()) == []


def test_feed_rotates_window_and_advances_cursor(tmp_path):
    c = _cache(tmp_path, {"A": "a.ua", "B": "b.ua", "C": "c.ua", "D": "d.ua"})
    feed = OsmDomainFeed(c, per_pass=2)
    assert [x.name for x in feed.candidates(set())] == ["A", "B"]
    assert [x.name for x in feed.candidates(set())] == ["C", "D"]
    assert [x.name for x in feed.candidates(set())] == ["A", "B"]   # wrapped
