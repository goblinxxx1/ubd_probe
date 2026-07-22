import hashlib
import json
import logging
from urllib.parse import urljoin, urlsplit

import httpx
from selectolax.parser import HTMLParser

from crawler.discovery.geo import find_city
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


def _extract_site_name(tree) -> str | None:
    node = tree.css_first('meta[property="og:site_name"]')
    if node is not None and node.attributes.get("content"):
        return node.attributes["content"].strip()
    for css in ("title", "h1"):
        node = tree.css_first(css)
        if node is not None:
            txt = node.text(strip=True)
            if txt:
                return txt
    return None


def _locality_from_jsonld(data) -> str | None:
    if isinstance(data, dict):
        addr = data.get("address")
        if isinstance(addr, dict):
            loc = addr.get("addressLocality")
            if isinstance(loc, str) and loc.strip():
                return loc.strip()
        if isinstance(addr, list):
            for a in addr:
                if isinstance(a, dict):
                    loc = a.get("addressLocality")
                    if isinstance(loc, str) and loc.strip():
                        return loc.strip()
        loc = data.get("addressLocality")
        if isinstance(loc, str) and loc.strip():
            return loc.strip()
        for key in ("@graph", "itemListElement"):
            if key in data:
                found = _locality_from_jsonld(data[key])
                if found:
                    return found
    elif isinstance(data, list):
        for entry in data:
            found = _locality_from_jsonld(entry)
            if found:
                return found
    return None


def _extract_locality(tree) -> str | None:
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        loc = _locality_from_jsonld(data)
        if loc:
            return loc
    node = tree.css_first('meta[property="business:contact_data:locality"]')
    if node is not None and node.attributes.get("content"):
        return node.attributes["content"].strip()
    for css in ('meta[property="og:locality"]', 'meta[name="geo.placename"]'):
        node = tree.css_first(css)
        if node is not None and node.attributes.get("content"):
            return node.attributes["content"].strip()
    node = tree.css_first('[itemprop="addressLocality"]')
    if node is not None:
        txt = node.text(strip=True)
        if txt:
            return txt
    parts = []
    for css in ("address", "footer", '[class*="contact"]', '[id*="contact"]',
                '[class*="address"]', '[class*="footer"]'):
        for n in tree.css(css):
            t = n.text(separator=" ", strip=True)
            if t:
                parts.append(t)
    return find_city(" ".join(parts))


def _has_offer_schema(tree) -> bool:
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text() or ""
        if '"offer"' in raw.lower():
            return True
    return False


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
            site_name = _extract_site_name(tree)
            locality = _extract_locality(tree)
            has_offer = _has_offer_schema(tree)
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
                                     logo_url=logo, site_name=site_name,
                                     locality=locality, has_offer_schema=has_offer))
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
