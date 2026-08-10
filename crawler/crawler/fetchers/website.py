import hashlib
import json
import logging
import re
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


_TAGLINE_SELECTORS = (
    ".site-description", ".tagline", "[class*='slogan']",   # header near-logo tagline
    ".tb-footer-desc", "[class*='footer-desc']",            # footer business description
)


def _cap_tagline(s: str, n: int = 160) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else (s[:n].rsplit(" ", 1)[0] or s[:n])


def _extract_site_tagline(tree) -> str | None:
    for css in _TAGLINE_SELECTORS:
        node = tree.css_first(css)
        if node is not None:
            txt = node.text(separator=" ", strip=True)
            if txt:
                return _cap_tagline(txt)
    node = tree.css_first('meta[name="description"]')
    if node is not None:
        txt = (node.attributes.get("content") or "").strip()
        if txt:
            return _cap_tagline(txt)
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


_OFFER_TYPE = re.compile(r'"@type"\s*:\s*"[^"]*offer', re.IGNORECASE)


def _has_offer_schema(tree) -> bool:
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text() or ""
        if _OFFER_TYPE.search(raw):
            return True
    return False


_ARTICLE_TYPE = re.compile(
    r'"@type"\s*:\s*"[^"]*(?:NewsArticle|BlogPosting|LiveBlogPosting|Report|Article)',
    re.IGNORECASE)
# physical-business types only — NOT generic "Organization" (a news site is a
# NewsMediaOrganization, which must not count as a business signal).
_BUSINESS_TYPE = re.compile(
    r'"@type"\s*:\s*"[^"]*(?:LocalBusiness|Store|Restaurant|CafeOrCoffeeShop)',
    re.IGNORECASE)


def _has_article_schema(tree) -> bool:
    for node in tree.css('script[type="application/ld+json"]'):
        if _ARTICLE_TYPE.search(node.text() or ""):
            return True
    return False


def _has_article_og(tree) -> bool:
    """OpenGraph og:type=article — set by most news/blog CMSes even with no
    schema.org JSON-LD. Schema-independent media signal."""
    node = tree.css_first('meta[property="og:type"]')
    return bool(node) and "article" in (node.attributes.get("content") or "").lower()


# Dated permalink: /YYYY/MM[/DD]/… — a news/blog URL convention. Business discount
# pages practically never carry dated permalinks, so this is a low-false-positive
# media signal. YYYY constrained to 19xx/20xx so catalog ids (/1234/56) don't match.
_DATED_PERMALINK = re.compile(r"/(?:19|20)\d\d/(?:0?[1-9]|1[0-2])(?:/\d{1,2})?(?:[/?#]|$)")


def _url_dated_permalink(url: str) -> bool:
    from urllib.parse import urlsplit
    return bool(_DATED_PERMALINK.search(urlsplit(url or "").path))


def _has_business_schema(tree) -> bool:
    for node in tree.css('script[type="application/ld+json"]'):
        if _BUSINESS_TYPE.search(node.text() or ""):
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
            site_tagline = _extract_site_tagline(tree)
            locality = _extract_locality(tree)
            has_offer = _has_offer_schema(tree)
            is_article = (_has_article_schema(tree) or _has_article_og(tree)
                          or _url_dated_permalink(url))
            has_business = _has_business_schema(tree)
            items: list[RawItem] = []
            seen_keys: set[str] = set()
            for node in tree.css("article, li, p"):
                if self._has_block_descendant(node):
                    continue  # keep the innermost (leaf) block = one paragraph
                text = node.text(separator=" ", strip=True)
                if len(text) < _MIN_LEN:
                    continue
                key = hashlib.sha1(text.encode("utf-8")).hexdigest()
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                # Links can sit between paragraphs (siblings of <p>, children of the
                # wrapping <article>): scope link capture to the outermost block
                # ancestor so per-paragraph items don't drop the offer's link.
                link_scope = self._outermost_block(node)
                links = [a.attributes.get("href") for a in link_scope.css("a")
                         if a.attributes.get("href")]
                items.append(RawItem(source_id=source["id"], platform="website",
                                     key=key, text=text, url=url, links=links,
                                     logo_url=logo, site_name=site_name,
                                     site_tagline=site_tagline,
                                     locality=locality, has_offer_schema=has_offer,
                                     is_article=is_article,
                                     has_business_schema=has_business))
            new_key = items[-1].key if items else last_seen_key
            return items, new_key
        except Exception as exc:  # noqa: BLE001 — never raise up the stack
            log.warning("website fetch failed for %s: %s", url, exc)
            return [], last_seen_key

    @staticmethod
    def _has_block_descendant(node) -> bool:
        # Walk descendants (css_first would match `node` itself). A block that
        # contains another block is a wrapper, not a leaf paragraph — skip it.
        child = node.child
        while child is not None:
            if child.tag in _BLOCK_TAGS or WebsiteFetcher._has_block_descendant(child):
                return True
            child = child.next
        return False

    @staticmethod
    def _outermost_block(node):
        """Highest matched-block ancestor of `node` (or `node` itself). Used to
        scope link capture up to the wrapping <article>/<li>."""
        top = node
        parent = node.parent
        while parent is not None:
            if parent.tag in _BLOCK_TAGS:
                top = parent
            parent = parent.parent
        return top
