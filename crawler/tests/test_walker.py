# crawler/tests/test_walker.py
from crawler.discovery import walker as walker_mod
from crawler.discovery.walker import DomainWalker, WalkPlan
from crawler.models import SourceCandidate


class NoWait:
    def wait(self, *a, **k):
        pass


class FakeRobots:
    """ParsedRobots stand-in."""
    def __init__(self, sitemaps=None, crawl_delay=None, disallow=()):
        self._sm = sitemaps or []
        self._cd = crawl_delay
        self._disallow = tuple(disallow)

    def can_fetch(self, url):
        return not any(d in url for d in self._disallow)

    def crawl_delay(self):
        return self._cd

    def sitemaps(self):
        return list(self._sm)


class FakePolicy:
    def __init__(self, parsed):
        self._parsed = parsed

    def get(self, domain):
        return self._parsed


def _cand(url="https://shop.ua"):
    return SourceCandidate(name="Shop", type="website", url_or_handle=url)


def test_sitemap_path_filters_promo_homepage_first_and_caps(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/akcii", "https://shop.ua/product/1",
                                         "https://shop.ua/promo", "https://shop.ua/blog"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/sitemap.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=2, bfs_trigger_min=1)
    plan = w.walk(_cand())
    assert isinstance(plan, WalkPlan)
    assert plan.domain == "shop.ua"
    assert plan.urls[0] == "https://shop.ua"          # homepage first
    assert plan.urls == ["https://shop.ua", "https://shop.ua/akcii"]  # capped at 2, promo only


def test_disallowed_urls_are_dropped(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/akcii", "https://shop.ua/promo"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"],
                                   disallow=("/promo",)))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand())
    assert "https://shop.ua/promo" not in plan.urls
    assert "https://shop.ua/akcii" in plan.urls


def test_disallowed_homepage_yields_no_urls(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])
    policy = FakePolicy(FakeRobots(disallow=("shop.ua",)))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait())
    plan = w.walk(_cand())
    assert plan.urls == []


def test_crawl_delay_is_clamped(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])
    policy = FakePolicy(FakeRobots(crawl_delay=9999.0))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_min_delay=3.0, crawl_delay_cap=30.0)
    plan = w.walk(_cand())
    assert plan.crawl_delay == 30.0


def test_bfs_fallback_when_sitemap_thin(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])

    # BFS fetches homepage HTML and follows same-domain promo links
    class HtmlResp:
        text = ('<a href="/akcii">s</a><a href="https://other.ua/promo">x</a>'
                '<a href="/product/1">p</a>')
        content = None
        status_code = 200

        def raise_for_status(self):
            pass

    class HtmlClient:
        def get(self, url, **kw):
            return HtmlResp()

    policy = FakePolicy(FakeRobots())
    w = DomainWalker(client=HtmlClient(), robots=policy, rate_limiter=NoWait(),
                     bfs_trigger_min=3, bfs_max_pages=3, domain_page_cap=10)
    plan = w.walk(_cand())
    assert "https://shop.ua/akcii" in plan.urls          # in-domain promo link found by BFS
    assert all("other.ua" not in u for u in plan.urls)   # off-domain dropped


def test_walk_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", boom)
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     bfs_trigger_min=99)
    plan = w.walk(_cand())
    assert plan.urls == ["https://shop.ua"]              # fallback to homepage


def test_info_pages_are_targeted_from_sitemap(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/kontakty",
                                         "https://shop.ua/product/1",
                                         "https://shop.ua/dostavka-i-oplata",
                                         "https://shop.ua/blog/post"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand())
    assert "https://shop.ua/kontakty" in plan.urls          # info page targeted
    assert "https://shop.ua/dostavka-i-oplata" in plan.urls
    assert "https://shop.ua/product/1" not in plan.urls     # excluded
    assert "https://shop.ua/blog/post" not in plan.urls     # excluded


def test_bfs_collects_target_by_anchor_and_skips_excluded(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])

    class HtmlResp:
        text = ('<a href="/page/12">Знижка для військовослужбовців</a>'
                '<a href="/product/9">Товар</a>'
                '<a href="/kontakty">Контакти</a>')
        content = None
        status_code = 200
        def raise_for_status(self): pass

    class HtmlClient:
        def get(self, url, **kw): return HtmlResp()

    policy = FakePolicy(FakeRobots())
    w = DomainWalker(client=HtmlClient(), robots=policy, rate_limiter=NoWait(),
                     bfs_trigger_min=3, bfs_max_pages=1, domain_page_cap=10)
    plan = w.walk(_cand())
    assert "https://shop.ua/page/12" in plan.urls           # target by anchor text
    assert "https://shop.ua/kontakty" in plan.urls          # target by slug
    assert "https://shop.ua/product/9" not in plan.urls     # excluded, not collected


def test_seed_gate_root_candidate_is_kept(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/akcii"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand("https://shop.ua"))                 # root candidate (passive)
    assert plan.urls[0] == "https://shop.ua"                # root always fetched


def test_seed_gate_product_candidate_url_is_dropped(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/akcii"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand("https://shop.ua/product/12"))      # active non-target candidate
    assert "https://shop.ua/product/12" not in plan.urls    # candidate URL not fetched
    assert "https://shop.ua/akcii" in plan.urls              # domain still walked
