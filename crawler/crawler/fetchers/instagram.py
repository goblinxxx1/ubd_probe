import logging

import httpx

from crawler.accounts.pool import AccountPool
from crawler.fetchers.ogmeta import fetch_og_item
from crawler.models import RawItem

log = logging.getLogger(__name__)


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
                 loader_factory=_default_loader_factory, max_posts: int = 12):
        self._pool = pool
        self._client = no_login_client
        self._loader_factory = loader_factory
        self._max_posts = max_posts

    def fetch(self, source: dict, last_seen_key: str | None):
        cred = self._pool.acquire()
        if cred is None:
            return self._no_login(source, last_seen_key)
        try:
            return self._logged_in(cred, source, last_seen_key)
        except Exception as exc:  # noqa: BLE001 — login/challenge/parse all degrade
            log.warning("instagram login/fetch failed for %s: %s", cred.username, exc)
            self._pool.mark_banned(cred.username)
            return self._no_login(source, last_seen_key)

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
