import logging

import httpx

from crawler.accounts.pool import AccountPool
from crawler.fetchers.ogmeta import fetch_og_item

log = logging.getLogger(__name__)


class FacebookFetcher:
    platform = "facebook"

    def __init__(self, pool: AccountPool, no_login_client: httpx.Client):
        self._pool = pool
        self._client = no_login_client

    def fetch(self, source: dict, last_seen_key: str | None):
        # Authenticated Facebook scraping has no reliable free library; the pool
        # is a documented hook for the future. Real path: public og:meta.
        _ = self._pool.acquire()
        return fetch_og_item(self._client, source, source["url_or_handle"],
                             "facebook", last_seen_key)
