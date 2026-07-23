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
    els = [{"tags": {"brand": "Aaa", "website": "https://same.ua"}},
           {"tags": {"brand": "Aaa", "website": "https://same.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://same.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://same.ua"}}]
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


def test_missing_brand_or_website_skipped():
    els = [{"tags": {"website": "https://x.ua"}},        # no brand
           {"tags": {"brand": "Y"}},                     # no website
           {"tags": {}}]
    assert _enum(els, min_pois=1).enumerate() == {}


def test_http_failure_returns_empty():
    assert _enum([], boom=True).enumerate() == {}
