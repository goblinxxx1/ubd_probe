import httpx

from crawler.fetchers.website import WebsiteFetcher, _extract_logo, _origin

PAGE = ('<html><head>'
        '<link rel="apple-touch-icon" href="/touch.png">'
        '<link rel="icon" href="/favicon.ico">'
        '</head><body><article>'
        'Знижка 20% для ветеранів. Діє до 31.12.2026. Завітайте до кафе.'
        '</article></body></html>')


def _client():
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=PAGE)))


def test_origin_derivation():
    assert _origin("https://shop.example.com/news/1") == "https://shop.example.com"


def test_logo_prefers_apple_touch_icon():
    from selectolax.parser import HTMLParser
    tree = HTMLParser(PAGE)
    assert _extract_logo(tree, "https://shop.example.com").endswith("/touch.png")


def test_website_item_has_page_url_and_logo():
    f = WebsiteFetcher(_client())
    items, _ = f.fetch({"id": 1, "type": "website",
                        "url_or_handle": "https://shop.example.com/news"}, None)
    assert items and items[0].url == "https://shop.example.com/news"
    assert items[0].logo_url.endswith("/touch.png")
