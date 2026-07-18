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


def test_website_never_raises_on_parse_error():
    # The HTTP request/status succeed cleanly (real MockTransport response,
    # so client.get()/raise_for_status() don't themselves raise); the failure
    # is forced downstream, in HTML parsing. The fetcher must still swallow
    # it and preserve the previous cursor key rather than propagating.
    with mock.patch("crawler.fetchers.website.HTMLParser", side_effect=RuntimeError("boom")):
        items, key = WebsiteFetcher(_client()).fetch(
            {"id": 1, "url_or_handle": "http://x"}, "prev")
    assert items == [] and key == "prev"
