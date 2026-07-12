from pathlib import Path

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


def test_website_never_raises_on_network_error():
    def boom(request):
        raise httpx.ConnectError("down")
    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(boom)))
    items, key = f.fetch({"id": 1, "url_or_handle": "http://x"}, "prev")
    assert items == [] and key == "prev"
