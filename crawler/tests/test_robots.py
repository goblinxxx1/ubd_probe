import json

from crawler.discovery.robots import ParsedRobots, RobotsPolicy


class FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, text="", status=200, boom=False):
        self._text, self._status, self._boom = text, status, boom
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        if self._boom:
            raise RuntimeError("network down")
        return FakeResp(self._text, self._status)


class NoWait:
    def wait(self, *a, **k):
        pass


ROBOTS_TXT = (
    "User-agent: *\n"
    "Disallow: /cart\n"
    "Crawl-delay: 7\n"
    "Sitemap: https://shop.ua/sitemap.xml\n"
    "Sitemap: https://shop.ua/sitemap-2.xml\n"
)


def test_parses_sitemaps_crawl_delay_and_disallow(tmp_path):
    client = FakeClient(text=ROBOTS_TXT)
    pol = RobotsPolicy(client, NoWait(), str(tmp_path / "r.json"), ttl_seconds=1000)
    r = pol.get("shop.ua")
    assert set(r.sitemaps()) == {"https://shop.ua/sitemap.xml", "https://shop.ua/sitemap-2.xml"}
    assert r.crawl_delay() == 7.0
    assert r.can_fetch("https://shop.ua/sale") is True
    assert r.can_fetch("https://shop.ua/cart") is False


def test_cache_persists_and_avoids_refetch(tmp_path):
    path = str(tmp_path / "r.json")
    client = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client, NoWait(), path, ttl_seconds=1000).get("shop.ua")
    assert client.calls == 1
    # a fresh policy reading the same file must NOT hit the network
    client2 = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client2, NoWait(), path, ttl_seconds=1000).get("shop.ua")
    assert client2.calls == 0
    saved = json.loads(open(path, encoding="utf-8").read())
    assert "shop.ua" in saved


def test_stale_entry_refetches(tmp_path):
    path = str(tmp_path / "r.json")
    clk = {"now": 1000.0}
    client = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client, NoWait(), path, ttl_seconds=100,
                 clock=lambda: clk["now"]).get("shop.ua")
    clk["now"] = 2000.0     # advance well past ttl
    client2 = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client2, NoWait(), path, ttl_seconds=100,
                 clock=lambda: clk["now"]).get("shop.ua")
    assert client2.calls == 1


def test_fetch_failure_allows_all(tmp_path):
    client = FakeClient(boom=True)
    pol = RobotsPolicy(client, NoWait(), str(tmp_path / "r.json"), ttl_seconds=1000)
    r = pol.get("shop.ua")
    assert r.can_fetch("https://shop.ua/cart") is True
    assert r.crawl_delay() is None
    assert r.sitemaps() == []


def test_corrupt_cache_file_starts_clean(tmp_path):
    path = str(tmp_path / "r.json")
    open(path, "w", encoding="utf-8").write("{not json")
    client = FakeClient(text=ROBOTS_TXT)
    pol = RobotsPolicy(client, NoWait(), path, ttl_seconds=1000)
    assert pol.get("shop.ua").crawl_delay() == 7.0
