import hashlib
import logging
from urllib.parse import urljoin, urlsplit

import httpx
from selectolax.parser import HTMLParser

from crawler.models import RawItem

log = logging.getLogger(__name__)
_MIN_LEN = 30
_BLOCK_TAGS = {"article", "li", "p"}


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


def _extract_logo(tree, base_url: str) -> str | None:
    # priority: apple-touch-icon -> og:image -> favicon
    for css, attr in (('link[rel="apple-touch-icon"]', "href"),
                      ('meta[property="og:image"]', "content"),
                      ('link[rel="icon"]', "href"),
                      ('link[rel="shortcut icon"]', "href")):
        node = tree.css_first(css)
        if node is not None:
            val = node.attributes.get(attr)
            if val:
                return urljoin(base_url, val)
    return None


class WebsiteFetcher:
    platform = "website"

    def __init__(self, client: httpx.Client):
        self._client = client

    def fetch(self, source: dict, last_seen_key: str | None):
        url = source["url_or_handle"]
        try:
            resp = self._client.get(url, follow_redirects=True)
            resp.raise_for_status()

            tree = HTMLParser(resp.text)
            logo = _extract_logo(tree, url)
            items: list[RawItem] = []
            seen_keys: set[str] = set()
            for node in tree.css("article, li, p"):
                if self._has_block_ancestor(node):
                    continue  # keep only the outermost matched block
                text = node.text(separator=" ", strip=True)
                if len(text) < _MIN_LEN:
                    continue
                key = hashlib.sha1(text.encode("utf-8")).hexdigest()
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                links = [a.attributes.get("href") for a in node.css("a")
                         if a.attributes.get("href")]
                items.append(RawItem(source_id=source["id"], platform="website",
                                     key=key, text=text, url=url, links=links,
                                     logo_url=logo))
            new_key = items[-1].key if items else last_seen_key
            return items, new_key
        except Exception as exc:  # noqa: BLE001 — never raise up the stack
            log.warning("website fetch failed for %s: %s", url, exc)
            return [], last_seen_key

    @staticmethod
    def _has_block_ancestor(node) -> bool:
        parent = node.parent
        while parent is not None:
            if parent.tag in _BLOCK_TAGS:
                return True
            parent = parent.parent
        return False
