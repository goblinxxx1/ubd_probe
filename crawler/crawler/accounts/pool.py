import logging
from datetime import datetime, timezone

from crawler.models import BotCredential

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AccountPool:
    def __init__(self, platform: str, credentials: list[BotCredential], api_client, now=_now):
        self._platform = platform
        self._creds = {c.username: c for c in credentials}
        self._order = [c.username for c in credentials]
        self._api = api_client
        self._now = now
        self._states: dict | None = None  # lazy — no I/O in __init__

    def _ensure_loaded(self) -> None:
        if self._states is not None:
            return
        try:
            self._states = {a["username"]: a
                            for a in self._api.list_bot_accounts(self._platform)}
        except Exception as exc:  # noqa: BLE001 — treat as all-unknown/active
            log.warning("could not load bot-account state for %s: %s", self._platform, exc)
            self._states = {}

    def acquire(self) -> BotCredential | None:
        self._ensure_loaded()
        now = self._now()
        for username in self._order:
            st = self._states.get(username)
            if st is None:
                return self._creds[username]
            state = st.get("state")
            if state == "banned":
                continue
            if state == "cooldown":
                cu = st.get("cooldown_until")
                if cu:
                    until = datetime.fromisoformat(cu)
                    if until.tzinfo is None:
                        until = until.replace(tzinfo=timezone.utc)
                    if until > now:
                        continue
            return self._creds[username]
        return None

    def mark_banned(self, username: str) -> None:
        self._ensure_loaded()
        self._states[username] = {"username": username, "state": "banned", "cooldown_until": None}
        try:
            self._api.set_bot_account_state(self._platform, username, "banned")
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to persist ban for %s: %s", username, exc)

    def mark_cooldown(self, username: str, until: datetime) -> None:
        self._ensure_loaded()
        iso = until.isoformat()
        self._states[username] = {"username": username, "state": "cooldown", "cooldown_until": iso}
        try:
            self._api.set_bot_account_state(self._platform, username, "cooldown", cooldown_until=iso)
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to persist cooldown for %s: %s", username, exc)
