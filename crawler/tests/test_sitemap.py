import gzip

from crawler.discovery.sitemap import collect_sitemap_urls


class NoWait:
    def wait(self, *a, **k):
        pass


URLSET = (
    '<?xml version="1.0"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    '<url><loc>https://shop.ua/sale</loc></url>'
    '<url><loc>https://shop.ua/product/1</loc></url>'
    '</urlset>'
)
INDEX = (
    '<?xml version="1.0"?>'
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    '<sitemap><loc>https://shop.ua/child.xml</loc></sitemap>'
    '</sitemapindex>'
)


class Resp:
    def __init__(self, content, text=None, status=200):
        self.content = content
        self.text = text if text is not None else (
            content.decode("utf-8", "replace") if isinstance(content, bytes) else content)
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class MapClient:
    def __init__(self, mapping):
        self._m = mapping
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        body = self._m[url]
        return Resp(body if isinstance(body, bytes) else body.encode())


def test_urlset_returns_locs():
    client = MapClient({"https://shop.ua/sitemap.xml": URLSET})
    urls = collect_sitemap_urls(["https://shop.ua/sitemap.xml"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert urls == ["https://shop.ua/sale", "https://shop.ua/product/1"]


def test_index_recurses_into_children():
    client = MapClient({"https://shop.ua/root.xml": INDEX,
                        "https://shop.ua/child.xml": URLSET})
    urls = collect_sitemap_urls(["https://shop.ua/root.xml"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert "https://shop.ua/sale" in urls


def test_gzip_sitemap_is_decoded():
    client = MapClient({"https://shop.ua/sitemap.xml.gz": gzip.compress(URLSET.encode())})
    urls = collect_sitemap_urls(["https://shop.ua/sitemap.xml.gz"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert "https://shop.ua/sale" in urls


def test_max_docs_caps_fetches():
    client = MapClient({"https://shop.ua/root.xml": INDEX,
                        "https://shop.ua/child.xml": URLSET})
    collect_sitemap_urls(["https://shop.ua/root.xml"], client, NoWait(),
                         "shop.ua", None, max_docs=1)
    assert client.calls == ["https://shop.ua/root.xml"]  # child not fetched


def test_malformed_xml_yields_empty():
    client = MapClient({"https://shop.ua/sitemap.xml": "<not-xml"})
    urls = collect_sitemap_urls(["https://shop.ua/sitemap.xml"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert urls == []


_INDEX_MIXED = (
    '<?xml version="1.0"?>'
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    '<sitemap><loc>https://shop.ua/sitemap-pt-product-2025-01.xml</loc></sitemap>'
    '<sitemap><loc>https://shop.ua/sitemap-page.xml</loc></sitemap>'
    '</sitemapindex>'
)
_PAGE_URLSET = (
    '<?xml version="1.0"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    '<url><loc>https://shop.ua/veterans</loc></url>'
    '</urlset>'
)


def test_product_child_sitemap_is_skipped():
    client = MapClient({
        "https://shop.ua/root.xml": _INDEX_MIXED,
        "https://shop.ua/sitemap-pt-product-2025-01.xml": URLSET,
        "https://shop.ua/sitemap-page.xml": _PAGE_URLSET,
    })
    urls = collect_sitemap_urls(["https://shop.ua/root.xml"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    # product catalog never fetched; page sitemap is
    assert "https://shop.ua/sitemap-pt-product-2025-01.xml" not in client.calls
    assert "https://shop.ua/sitemap-page.xml" in client.calls
    assert urls == ["https://shop.ua/veterans"]


_INDEX_NEWS = (
    '<?xml version="1.0"?>'
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    '<sitemap><loc>https://mrpl.city/sitemap_news_mariupol.xml</loc></sitemap>'
    '<sitemap><loc>https://mrpl.city/sitemap-page.xml</loc></sitemap>'
    '</sitemapindex>'
)


def test_excluded_child_sitemap_is_skipped():
    # news/blog/tag child sitemaps list only excluded pages — never download them
    client = MapClient({
        "https://mrpl.city/root.xml": _INDEX_NEWS,
        "https://mrpl.city/sitemap_news_mariupol.xml": URLSET,
        "https://mrpl.city/sitemap-page.xml": _PAGE_URLSET,
    })
    urls = collect_sitemap_urls(["https://mrpl.city/root.xml"], client, NoWait(),
                                "mrpl.city", None, max_docs=10)
    assert "https://mrpl.city/sitemap_news_mariupol.xml" not in client.calls  # news skipped
    assert "https://mrpl.city/sitemap-page.xml" in client.calls               # page fetched
    assert urls == ["https://shop.ua/veterans"]     # only the non-news child's page (from _PAGE_URLSET)


def test_early_stop_once_enough_promo_pages():
    big = ('<?xml version="1.0"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>https://shop.ua/sale</loc></url>'      # promo
           '<url><loc>https://shop.ua/promo</loc></url>'     # promo -> target reached here
           '<url><loc>https://shop.ua/never-reached</loc></url>'
           '</urlset>')
    client = MapClient({"https://shop.ua/s.xml": big, "https://shop.ua/s2.xml": URLSET})
    urls = collect_sitemap_urls(["https://shop.ua/s.xml", "https://shop.ua/s2.xml"], client,
                                NoWait(), "shop.ua", None, max_docs=10,
                                promo_filter=lambda u: "/sale" in u or "/promo" in u,
                                promo_target=2)
    assert "https://shop.ua/s2.xml" not in client.calls   # stopped before the 2nd doc
    assert urls == ["https://shop.ua/sale", "https://shop.ua/promo"]  # returned at target
