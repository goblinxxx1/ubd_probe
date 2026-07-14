from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx
import instaloader.exceptions as ie

from crawler.accounts.pool import AccountPool
from crawler.fetchers.instagram import InstagramFetcher
from crawler.models import BotCredential

OG_HTML = ('<html><head>'
           '<meta property="og:title" content="Shop (@shop)">'
           '<meta property="og:description" content="Знижка 25% для ветеранів">'
           '</head></html>')

T0 = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


class FakeApi:
    def list_bot_accounts(self, platform): return []
    def set_bot_account_state(self, *a, **k): self.last = (a, k); return {}


class Clock:
    """Mutable, injectable UTC clock shared by pool + fetcher in tests."""
    def __init__(self, t=T0): self.t = t
    def __call__(self): return self.t


def _loader_raising(exc):
    class BoomLoader:
        context = None
        def login(self, u, p): raise exc
    return lambda: BoomLoader()


def _no_login_client():
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=OG_HTML)))


def test_degrades_to_og_meta_when_pool_empty():
    pool = AccountPool("instagram", [], FakeApi())      # no creds → acquire() None
    f = InstagramFetcher(pool, _no_login_client(), loader_factory=lambda: None)
    items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    assert len(items) == 1
    assert "Знижка 25%" in items[0].text
    assert items[0].platform == "instagram"


def test_real_challenge_marks_banned_and_degrades():
    # A login-level challenge (2FA/checkpoint) is a genuine account rejection →
    # permanent ban until a human rotates the credential.
    clock = Clock()
    api = FakeApi()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], api, now=clock)
    f = InstagramFetcher(pool, _no_login_client(), now=clock,
                         loader_factory=_loader_raising(ie.TwoFactorAuthRequiredException("2fa")))
    items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    assert len(items) == 1 and "Знижка 25%" in items[0].text  # degraded result
    assert pool.acquire() is None                        # bot_a banned now...
    clock.t = T0 + timedelta(days=365)
    assert pool.acquire() is None                        # ...and still banned much later


def test_bad_credentials_marks_banned():
    clock = Clock()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], FakeApi(), now=clock)
    f = InstagramFetcher(pool, _no_login_client(), now=clock,
                         loader_factory=_loader_raising(ie.BadCredentialsException("bad")))
    f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    clock.t = T0 + timedelta(days=365)
    assert pool.acquire() is None                        # permanent ban


def test_transient_connection_error_marks_cooldown_not_banned():
    clock = Clock()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], FakeApi(), now=clock)
    f = InstagramFetcher(pool, _no_login_client(), now=clock, cooldown=timedelta(hours=1),
                         loader_factory=_loader_raising(ie.ConnectionException("network down")))
    items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    assert len(items) == 1                               # degraded to og:meta
    assert pool.acquire() is None                        # unavailable during cooldown
    clock.t = T0 + timedelta(hours=2)
    assert pool.acquire() is not None                    # recovers → was cooldown, not ban


def test_rate_limit_marks_cooldown():
    clock = Clock()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], FakeApi(), now=clock)
    f = InstagramFetcher(pool, _no_login_client(), now=clock, cooldown=timedelta(hours=1),
                         loader_factory=_loader_raising(ie.TooManyRequestsException("429")))
    f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    assert pool.acquire() is None
    clock.t = T0 + timedelta(hours=2)
    assert pool.acquire() is not None                    # temporary back-off only


def test_unknown_error_defaults_to_cooldown_not_ban():
    # A plain, unclassifiable error must NOT permanently ban the account.
    clock = Clock()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], FakeApi(), now=clock)
    f = InstagramFetcher(pool, _no_login_client(), now=clock, cooldown=timedelta(hours=1),
                         loader_factory=_loader_raising(RuntimeError("mystery")))
    f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    clock.t = T0 + timedelta(hours=2)
    assert pool.acquire() is not None                    # recovers → conservative cooldown


def test_missing_instaloader_does_not_penalize_account():
    # instaloader absent is environmental — it would fail every account identically.
    # The credential must be left untouched (never mark the whole pool banned).
    clock = Clock()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], FakeApi(), now=clock)
    f = InstagramFetcher(pool, _no_login_client(), now=clock,
                         loader_factory=_loader_raising(ImportError("No module named 'instaloader'")))
    items, key = f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    assert len(items) == 1                               # degraded
    clock.t = T0 + timedelta(days=365)
    assert pool.acquire() is not None                    # account never penalised


def test_missing_profile_does_not_penalize_account():
    # ProfileNotExists is the source's fault, not the account's.
    clock = Clock()
    pool = AccountPool("instagram", [BotCredential("instagram", "bot_a", "pw")], FakeApi(), now=clock)
    f = InstagramFetcher(pool, _no_login_client(), now=clock,
                         loader_factory=_loader_raising(ie.ProfileNotExistsException("gone")))
    f.fetch({"id": 3, "url_or_handle": "https://instagram.com/shop"}, None)
    clock.t = T0 + timedelta(days=365)
    assert pool.acquire() is not None                    # account healthy


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
