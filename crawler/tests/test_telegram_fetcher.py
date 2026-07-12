from pathlib import Path

import httpx

from crawler.fetchers.telegram import TelegramFetcher

FIX = (Path(__file__).parent / "fixtures" / "telegram_channel.html").read_text(encoding="utf-8")


def _fetcher():
    def handle(request):
        assert "/s/" in request.url.path
        return httpx.Response(200, text=FIX)
    return TelegramFetcher(httpx.Client(transport=httpx.MockTransport(handle)))


def test_telegram_parses_messages_and_handle():
    f = _fetcher()
    items, new_key = f.fetch({"id": 5, "url_or_handle": "https://t.me/chan"}, None)
    assert len(items) == 2
    assert items[0].key == "chan/10"
    assert any("Знижка 30%" in i.text for i in items)
    assert new_key == "chan/11"


def test_telegram_skips_already_seen():
    f = _fetcher()
    items, new_key = f.fetch({"id": 5, "url_or_handle": "@chan"}, "chan/10")
    assert [i.key for i in items] == ["chan/11"]
    assert new_key == "chan/11"


def test_telegram_never_raises():
    def boom(request):
        raise httpx.ConnectError("down")
    f = TelegramFetcher(httpx.Client(transport=httpx.MockTransport(boom)))
    items, key = f.fetch({"id": 5, "url_or_handle": "@chan"}, "prev")
    assert items == [] and key == "prev"
