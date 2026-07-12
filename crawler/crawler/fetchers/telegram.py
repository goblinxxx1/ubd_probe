import logging
import re

import httpx
from selectolax.parser import HTMLParser

from crawler.models import RawItem

log = logging.getLogger(__name__)
_HANDLE = re.compile(r"(?:t\.me/|@)?([A-Za-z0-9_]+)/?$")


def _handle_of(url_or_handle: str) -> str:
    m = _HANDLE.search(url_or_handle.strip())
    return m.group(1) if m else url_or_handle.strip().lstrip("@")


class TelegramFetcher:
    platform = "telegram"

    def __init__(self, client: httpx.Client):
        self._client = client

    def fetch(self, source: dict, last_seen_key: str | None):
        handle = _handle_of(source["url_or_handle"])
        try:
            resp = self._client.get(f"https://t.me/s/{handle}", follow_redirects=True)
            resp.raise_for_status()

            tree = HTMLParser(resp.text)
            items: list[RawItem] = []
            for msg in tree.css(".tgme_widget_message"):
                key = msg.attributes.get("data-post")
                if not key:
                    continue
                if last_seen_key is not None and key == last_seen_key:
                    continue
                body = msg.css_first(".tgme_widget_message_text")
                text = body.text(separator=" ", strip=True) if body else ""
                links = [a.attributes.get("href") for a in msg.css("a")
                         if a.attributes.get("href")]
                items.append(RawItem(source_id=source["id"], platform="telegram",
                                     key=key, text=text, url=f"https://t.me/{key}", links=links))

            new_key = items[-1].key if items else last_seen_key
            return items, new_key
        except Exception as exc:  # noqa: BLE001 — never raise up the stack
            log.warning("telegram fetch failed for %s: %s", handle, exc)
            return [], last_seen_key
