import httpx

from crawler.accounts.pool import AccountPool
from crawler.fetchers.facebook import FacebookFetcher

OG_HTML = ('<html><head>'
           '<meta property="og:title" content="Кафе Львів">'
           '<meta property="og:description" content="Акція: -20% для військових">'
           '</head></html>')


class FakeApi:
    def list_bot_accounts(self, platform): return []
    def set_bot_account_state(self, *a, **k): return {}


def test_facebook_reads_og_meta():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=OG_HTML)))
    f = FacebookFetcher(AccountPool("facebook", [], FakeApi()), client)
    items, key = f.fetch({"id": 8, "url_or_handle": "https://facebook.com/cafe"}, None)
    assert len(items) == 1
    assert "-20%" in items[0].text
    assert items[0].platform == "facebook"


def test_facebook_never_raises():
    def boom(r): raise httpx.ConnectError("down")
    f = FacebookFetcher(AccountPool("facebook", [], FakeApi()),
                        httpx.Client(transport=httpx.MockTransport(boom)))
    items, key = f.fetch({"id": 8, "url_or_handle": "https://facebook.com/cafe"}, "prev")
    assert items == [] and key == "prev"
