from pathlib import Path
from unittest import mock

import httpx

from crawler.fetchers.website import WebsiteFetcher

FIX = (Path(__file__).parent / "fixtures" / "website_offers.html").read_text(encoding="utf-8")


def _client():
    def handle(request):
        return httpx.Response(200, text=FIX)
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_website_extracts_text_blocks_and_links():
    f = WebsiteFetcher(_client())
    items, new_key = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    texts = [i.text for i in items]
    assert any("Знижка 15%" in t for t in texts)
    assert any("музею" in t for t in texts)
    assert all(i.platform == "website" for i in items)
    # short "Коротко" block is filtered out
    assert not any(i.text.strip() == "Коротко" for i in items)
    # link captured
    assert any("t.me/coffeechan" in "".join(i.links) for i in items)
    assert new_key is not None


def test_website_no_duplicate_or_overlapping_blocks():
    # fixture has 2 real offers (nested <article><p>...) plus one filtered-out
    # short block; each offer must be emitted exactly once, not once per
    # matched ancestor/descendant pair.
    f = WebsiteFetcher(_client())
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert len(items) == 2
    keys = [i.key for i in items]
    assert len(keys) == len(set(keys))
    # the offer block that had a link still carries it
    discount_item = next(i for i in items if "Знижка 15%" in i.text)
    assert any("t.me/coffeechan" in link for link in discount_item.links)


def test_website_captures_site_name():
    html = ('<html><head><meta property="og:site_name" content="My Cafe">'
            '<title>t</title></head><body>'
            '<article><p>Знижка 15% для ветеранів на каву у нас.</p></article>'
            '</body></html>')
    def handle(request):
        return httpx.Response(200, text=html)
    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.site_name == "My Cafe" for i in items)


def test_website_never_raises_on_network_error():
    def boom(request):
        raise httpx.ConnectError("down")
    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(boom)))
    items, key = f.fetch({"id": 1, "url_or_handle": "http://x"}, "prev")
    assert items == [] and key == "prev"


def test_website_locality_from_jsonld():
    html = ('<html><head><script type="application/ld+json">'
            '{"@type":"Restaurant","address":{"@type":"PostalAddress",'
            '"addressLocality":"Львів"}}</script></head><body>'
            '<article><p>Знижка 15% для ветеранів на каву у нас сьогодні.</p>'
            '</article></body></html>')

    def handle(request):
        return httpx.Response(200, text=html)

    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality == "Львів" for i in items)


def test_website_locality_from_og_meta():
    html = ('<html><head><meta property="og:locality" content="Одеса"></head>'
            '<body><article><p>Знижка 15% для ветеранів на каву у нас сьогодні.'
            '</p></article></body></html>')

    def handle(request):
        return httpx.Response(200, text=html)

    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality == "Одеса" for i in items)


def test_website_locality_absent_is_none():
    f = WebsiteFetcher(_client())
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality is None for i in items)


def test_website_never_raises_on_parse_error():
    # The HTTP request/status succeed cleanly (real MockTransport response,
    # so client.get()/raise_for_status() don't themselves raise); the failure
    # is forced downstream, in HTML parsing. The fetcher must still swallow
    # it and preserve the previous cursor key rather than propagating.
    with mock.patch("crawler.fetchers.website.HTMLParser", side_effect=RuntimeError("boom")):
        items, key = WebsiteFetcher(_client()).fetch(
            {"id": 1, "url_or_handle": "http://x"}, "prev")
    assert items == [] and key == "prev"


def test_locality_from_microdata():
    from selectolax.parser import HTMLParser
    from crawler.fetchers.website import _extract_locality
    html = '<html><body><span itemprop="addressLocality">Київ</span></body></html>'
    assert _extract_locality(HTMLParser(html)) == "Київ"


def test_locality_from_contact_region():
    from selectolax.parser import HTMLParser
    from crawler.fetchers.website import _extract_locality
    html = ('<html><body><main><p>Знижка 15% для УБД</p></main>'
            '<footer><address>м. Вишневе, вул. Київська 1</address></footer>'
            '</body></html>')
    assert _extract_locality(HTMLParser(html)) == "Вишневе"


def test_offer_schema_flag_set(monkeypatch):
    from crawler.fetchers.website import WebsiteFetcher
    html = ('<html><body><article>'
            'Знижка 20% для ветеранів у кафе на розі, діє до 31.12'
            '<script type="application/ld+json">'
            '{"@type":"Offer","price":"100"}</script>'
            '</article></body></html>')

    class _Resp:
        text = html
        def raise_for_status(self): pass

    class _Client:
        def get(self, url, follow_redirects=True): return _Resp()

    items, _ = WebsiteFetcher(_Client()).fetch(
        {"id": 1, "url_or_handle": "http://shop.ua"}, None)
    assert items and items[0].has_offer_schema is True


def test_offer_schema_flag_not_set_for_incidental_word():
    from crawler.fetchers.website import WebsiteFetcher
    html = ('<html><body><article>'
            'Знижка 20% для ветеранів у кафе на розі, діє до 31.12'
            '<script type="application/ld+json">'
            # квотований "offer" у ЧУЖОМУ полі (не @type) — тригерив старий підрядковий
            # `"offer" in raw`, але новий regex прив'язаний до @type → має бути False
            '{"@type":"Article","category":"offer"}</script>'
            '</article></body></html>')

    class _Resp:
        text = html
        def raise_for_status(self): pass

    class _Client:
        def get(self, url, follow_redirects=True): return _Resp()

    items, _ = WebsiteFetcher(_Client()).fetch(
        {"id": 1, "url_or_handle": "http://shop.ua"}, None)
    assert items and items[0].has_offer_schema is False


def _fetcher_returning(html):
    def handle(request):
        return httpx.Response(200, text=html)
    return WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))


def test_news_article_schema_sets_is_article(monkeypatch):
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"NewsArticle","headline":"Знижки для ветеранів"}'
            '</script></head><body>'
            '<article>Знижка 20% для ветеранів у місті детально розписана тут</article>'
            '</body></html>')
    f = _fetcher_returning(html)   # existing helper in this test module
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://news.example/a"}, None)
    assert items and items[0].is_article is True
    assert items[0].has_business_schema is False


def test_localbusiness_schema_sets_business_not_article(monkeypatch):
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"LocalBusiness","name":"Кафе"}'
            '</script></head><body>'
            '<p>Знижка 20% для ветеранів у нас щодня протягом місяця</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://cafe.example"}, None)
    assert items and items[0].is_article is False
    assert items[0].has_business_schema is True
