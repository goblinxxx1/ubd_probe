import logging
from datetime import datetime, timedelta, timezone

import httpx

from crawler.accounts.pool import AccountPool
from crawler.fetchers.ogmeta import fetch_og_item
from crawler.models import RawItem

log = logging.getLogger(__name__)

DEFAULT_COOLDOWN = timedelta(hours=1)

# Failure dispositions returned by _classify_failure.
_BAN = "ban"            # genuine account rejection/challenge — permanent until human rotates creds
_COOLDOWN = "cooldown"  # transient (network/rate-limit/unknown) — temporary back-off
_SKIP = "skip"          # not the account's fault (env missing / source gone) — leave state untouched


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _classify_failure(exc: Exception) -> str:
    """Decide how a logged-in-fetch failure should affect the credential.

    Previously any exception marked the account permanently banned — a missing
    instaloader import or a transient rate-limit would nuke the whole pool. We now
    reserve mark_banned for real account-level rejections and back off otherwise.
    """
    # instaloader absent → environmental, fails every account identically. Never penalise.
    if isinstance(exc, ImportError):
        return _SKIP
    try:
        import instaloader.exceptions as ie
    except ImportError:
        return _COOLDOWN  # can't classify precisely; be conservative, avoid a permanent ban
    # Source-level problems: the account is healthy, the target profile isn't.
    if isinstance(exc, (ie.ProfileNotExistsException, ie.PrivateProfileNotFollowedException)):
        return _SKIP
    # Real account rejection / challenge: bad creds, 2FA/checkpoint, forced re-login, 403 block.
    if isinstance(exc, (ie.LoginException, ie.LoginRequiredException,
                        ie.QueryReturnedForbiddenException)):
        return _BAN
    # Network / rate-limit (ConnectionException, TooManyRequestsException) and anything
    # else unrecognised → temporary back-off rather than a permanent ban.
    return _COOLDOWN


def _default_loader_factory():
    import instaloader
    return instaloader.Instaloader(download_pictures=False, download_videos=False,
                                   download_comments=False, save_metadata=False)


def _handle_of(url_or_handle: str) -> str:
    s = url_or_handle.rstrip("/")
    return s.split("/")[-1].lstrip("@")


class InstagramFetcher:
    platform = "instagram"

    def __init__(self, pool: AccountPool, no_login_client: httpx.Client,
                 loader_factory=_default_loader_factory, max_posts: int = 12,
                 cooldown: timedelta = DEFAULT_COOLDOWN, now=_now_utc):
        self._pool = pool
        self._client = no_login_client
        self._loader_factory = loader_factory
        self._max_posts = max_posts
        self._cooldown = cooldown
        self._now = now

    def fetch(self, source: dict, last_seen_key: str | None):
        cred = self._pool.acquire()
        if cred is None:
            return self._no_login(source, last_seen_key)
        try:
            return self._logged_in(cred, source, last_seen_key)
        except Exception as exc:  # noqa: BLE001 — login/challenge/parse all degrade
            self._penalise(cred.username, exc)
            return self._no_login(source, last_seen_key)

    def _penalise(self, username: str, exc: Exception) -> None:
        action = _classify_failure(exc)
        if action == _BAN:
            log.warning("instagram account %s rejected (ban/challenge): %s", username, exc)
            self._pool.mark_banned(username)
        elif action == _COOLDOWN:
            until = self._now() + self._cooldown
            log.warning("instagram fetch transient failure for %s; cooldown until %s: %s",
                        username, until.isoformat(), exc)
            self._pool.mark_cooldown(username, until)
        else:  # _SKIP
            log.warning("instagram fetch failed for %s (not account fault, state untouched): %s",
                        username, exc)

    def _logged_in(self, cred, source, last_seen_key):
        import instaloader
        loader = self._loader_factory()
        loader.login(cred.username, cred.password)
        handle = _handle_of(source["url_or_handle"])
        profile = instaloader.Profile.from_username(loader.context, handle)
        items: list[RawItem] = []
        for post in profile.get_posts():
            key = post.shortcode
            if last_seen_key is not None and key == last_seen_key:
                break
            text = post.caption or ""
            items.append(RawItem(source_id=source["id"], platform="instagram", key=key,
                                 text=text, url=f"https://instagram.com/p/{key}"))
            if len(items) >= self._max_posts:
                break
        new_key = items[0].key if items else last_seen_key
        return items, new_key

    def _no_login(self, source, last_seen_key):
        return fetch_og_item(self._client, source, source["url_or_handle"],
                             "instagram", last_seen_key)
