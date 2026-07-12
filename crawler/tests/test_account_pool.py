from datetime import datetime, timedelta, timezone

from crawler.accounts.pool import AccountPool
from crawler.models import BotCredential


class FakeApi:
    def __init__(self, states):
        self._states = states
        self.calls = []

    def list_bot_accounts(self, platform):
        return self._states

    def set_bot_account_state(self, platform, username, state, cooldown_until=None, note=None):
        self.calls.append((platform, username, state, cooldown_until))
        return {}


def _creds():
    return [BotCredential("instagram", "bot_a", "p1"),
            BotCredential("instagram", "bot_b", "p2")]


def test_acquire_skips_banned():
    api = FakeApi([{"username": "bot_a", "state": "banned", "cooldown_until": None}])
    pool = AccountPool("instagram", _creds(), api)
    assert pool.acquire().username == "bot_b"


def test_acquire_skips_active_cooldown_but_uses_expired():
    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    future = (now + timedelta(hours=1)).isoformat()
    api = FakeApi([{"username": "bot_a", "state": "cooldown", "cooldown_until": future}])
    pool = AccountPool("instagram", _creds(), api, now=lambda: now)
    assert pool.acquire().username == "bot_b"

    past = (now - timedelta(hours=1)).isoformat()
    api2 = FakeApi([{"username": "bot_a", "state": "cooldown", "cooldown_until": past}])
    pool2 = AccountPool("instagram", _creds(), api2, now=lambda: now)
    assert pool2.acquire().username == "bot_a"  # cooldown expired


def test_mark_banned_persists_and_excludes():
    api = FakeApi([])
    pool = AccountPool("instagram", _creds(), api)
    pool.mark_banned("bot_a")
    assert ("instagram", "bot_a", "banned", None) in api.calls
    assert pool.acquire().username == "bot_b"


def test_all_unavailable_returns_none():
    api = FakeApi([{"username": "bot_a", "state": "banned", "cooldown_until": None},
                   {"username": "bot_b", "state": "banned", "cooldown_until": None}])
    pool = AccountPool("instagram", _creds(), api)
    assert pool.acquire() is None
