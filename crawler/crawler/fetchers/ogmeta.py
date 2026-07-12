import hashlib
import logging

from selectolax.parser import HTMLParser

from crawler.models import RawItem

log = logging.getLogger(__name__)


def _meta(tree, prop: str) -> str:
    node = tree.css_first(f'meta[property="{prop}"]')
    return (node.attributes.get("content") or "").strip() if node else ""


def fetch_og_item(client, source: dict, url: str, platform: str, last_seen_key):
    # NOTE: the whole body (including HTML parsing and RawItem construction)
    # is wrapped in the try — not just the HTTP GET — so that any downstream
    # parse failure also degrades gracefully instead of propagating. This
    # fetcher must never raise.
    try:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()

        tree = HTMLParser(resp.text)
        text = " ".join(x for x in (_meta(tree, "og:title"), _meta(tree, "og:description")) if x)
        if not text.strip():
            return [], last_seen_key
        key = hashlib.sha1(text.encode("utf-8")).hexdigest()
        item = RawItem(source_id=source["id"], platform=platform, key=key, text=text, url=url)
        return [item], key
    except Exception as exc:  # noqa: BLE001 — never raise up the stack
        log.warning("%s og:meta fetch failed for %s: %s", platform, url, exc)
        return [], last_seen_key
