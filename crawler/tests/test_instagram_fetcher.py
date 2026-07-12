from unittest import mock

import httpx

from crawler.accounts.pool import AccountPool
from crawler.fetchers.instagram import InstagramFetcher
from crawler.models import BotCredential

OG_HTML = ('<html><head>'
           '<meta property="og:title" content="Shop (@shop)">'
           '<meta property="og:description" content="Знижка 25% для ветеранів">'
           '</head></html>')


class FakeApi:
    def list_bot_accounts(self, platform): return []
    def set_bot_account_state(self, *a, **k): self.last = (a, k); return {}


def _no_login_client():
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=OG_HTML)))


def test_degrades_to_og_meta_when_pool_empty():
    pool = AccountPool("instagram", [], FakeApi())      # no creds → acquire() None
    f = InstagramFetcher(pool, _no_login_client(), loader_factory=lambda: None)
    items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    assert len(items) == 1
    assert "Знижка 25%" in items[0].text
    assert items[0].platform == "instagram"


def test_login_failure_marks_banned_and_degrades():
    api = FakeApi()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], api)

    class BoomLoader:
        context = None
        def login(self, u, p): raise RuntimeError("challenge_required")

    f = InstagramFetcher(pool, _no_login_client(), loader_factory=lambda: BoomLoader())
    items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    assert pool.acquire() is None              # bot_a now banned
    assert len(items) == 1 and "Знижка 25%" in items[0].text  # degraded result


def test_never_raises_on_total_failure():
    def boom(r): raise httpx.ConnectError("down")
    pool = AccountPool("instagram", [], FakeApi())
    f = InstagramFetcher(pool, httpx.Client(transport=httpx.MockTransport(boom)),
                         loader_factory=lambda: None)
    items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, "prev")
    assert items == [] and key == "prev"


def test_ogmeta_never_raises_on_parse_error():
    # The HTTP request/status succeed cleanly (real MockTransport response),
    # the failure is forced downstream in HTML parsing. The og:meta helper
    # (and by extension the instagram no-login degrade path) must swallow it
    # and preserve the previous cursor key rather than propagating.
    pool = AccountPool("instagram", [], FakeApi())
    f = InstagramFetcher(pool, _no_login_client(), loader_factory=lambda: None)
    with mock.patch("crawler.fetchers.ogmeta.HTMLParser", side_effect=RuntimeError("boom")):
        items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, "prev")
    assert items == [] and key == "prev"
