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
