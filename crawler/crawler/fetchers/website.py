import hashlib
import json
import logging
import re
from urllib.parse import urljoin, urlsplit

import httpx
from selectolax.parser import HTMLParser

from crawler.discovery.geo import find_city
from crawler.models import RawItem
from crawler.util.hosts import bare_host

log = logging.getLogger(__name__)
_MIN_LEN = 30
# Segment boundaries: every block-level *content* container. Offer text can live in
# ANY of these, not only <p>/<li>/<article> — a discount in a bare <div>, <section>
# or <td> was invisible before. Inline tags (<a>,<span>,<b>,<em>…) are NOT boundaries:
# their text bubbles up into the enclosing leaf via node.text(), so they never split a
# block. Pure wrappers (<ul>,<ol>,<table>,<tr>) are omitted — they always contain a
# block child, so the leaf filter would drop them anyway.
_BLOCK_TAGS = {
    "article", "section", "div", "li", "p", "td", "th", "dd", "dt",
    "blockquote", "figure", "figcaption", "main", "aside", "summary", "caption",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
_BLOCK_SELECTOR = ", ".join(sorted(_BLOCK_TAGS))
# Site chrome — never carries offer content; skip any candidate nested under these.
_CHROME_TAGS = {"nav", "header", "footer", "form"}
# Link-scope grouping: climb only through item-grouping containers (article/li), NOT
# generic divs, so a per-paragraph item still picks up a sibling link without vacuuming
# up every link on a page-wide wrapper <div>.
_LINK_SCOPE_TAGS = {"article", "li"}


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


_ORG_TYPES = {"organization", "localbusiness", "website"}


def _safe_url(base_url: str, val) -> str | None:
    """Resolve val against base_url; allow ONLY http/https; cap length. Blocks
    javascript:/data: and other schemes from ever reaching the DB or an <img src>."""
    if not val or not isinstance(val, str):
        return None
    absolute = urljoin(base_url, val.strip())
    if urlsplit(absolute).scheme not in ("http", "https"):
        return None
    return absolute[:1024]


def _extract_image(tree, base_url: str) -> str | None:
    # card HERO image, priority: apple-touch-icon -> og:image -> favicon
    for css, attr in (('link[rel="apple-touch-icon"]', "href"),
                      ('meta[property="og:image"]', "content"),
                      ('link[rel="icon"]', "href"),
                      ('link[rel="shortcut icon"]', "href")):
        node = tree.css_first(css)
        if node is not None:
            safe = _safe_url(base_url, node.attributes.get(attr))
            if safe:
                return safe
    return None


def _extract_canonical(tree, base_url: str) -> str | None:
    """Сайт сам оголошує канонічну URL сторінки (згортає фасети/пагінацію/utm-варіанти).
    Використовуємо як ідентичність офера для дедупу, з fallback на нашу канонікалізацію."""
    node = tree.css_first('link[rel="canonical"]')
    if node is not None:
        return _safe_url(base_url, node.attributes.get("href"))
    return None


def _find_logo(obj) -> str | None:
    """Recurse a parsed JSON-LD value for an Organization/LocalBusiness/WebSite
    `logo` (string or {url}). Handles list, @graph wrapper, and @type-as-list."""
    if isinstance(obj, list):
        for item in obj:
            got = _find_logo(item)
            if got:
                return got
        return None
    if not isinstance(obj, dict):
        return None
    if "@graph" in obj:
        got = _find_logo(obj["@graph"])
        if got:
            return got
    t = obj.get("@type")
    if isinstance(t, str):
        types = {t.lower()}
    elif isinstance(t, list):
        types = {x.lower() for x in t if isinstance(x, str)}
    else:
        types = set()
    if types & _ORG_TYPES:
        logo = obj.get("logo")
        if isinstance(logo, str):
            return logo
        if isinstance(logo, dict) and isinstance(logo.get("url"), str):
            return logo["url"]
    return None


def _jsonld_logo(tree) -> str | None:
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue                     # malformed block — skip, never crash
        got = _find_logo(data)
        if got:
            return got
    return None


def _extract_logo(tree, base_url: str) -> str | None:
    """Brand LOGO (SVG-friendly), best-source-first: JSON-LD Organization.logo ->
    <img class=logo> src -> apple-touch-icon. Returns a URL only (never inline SVG);
    http/https enforced by _safe_url. Distinct from the card hero (_extract_image)."""
    got = _safe_url(base_url, _jsonld_logo(tree))
    if got:
        return got
    for css in _LOGO_IMG_SELECTORS:
        node = tree.css_first(css)
        if node is not None:
            got = _safe_url(base_url, node.attributes.get("src"))
            if got:
                return got
    node = tree.css_first('link[rel="apple-touch-icon"]')
    if node is not None:
        return _safe_url(base_url, node.attributes.get("href"))
    return None


# Logo <img> containers, best-name-first. Scoping to logo/brand containers avoids
# unrelated page images (payment icons, partner badges) whose alt is not the business.
_LOGO_IMG_SELECTORS = (
    "img[class*=logo]", "[class*=logo] img", "[id*=logo] img",
    "a[class*=brand] img", "header a img",
)
# Generic alts that are not a business name — never use them as the provider.
_GENERIC_ALTS = {"logo", "лого", "image", "img", "banner", "банер", "home", "головна"}
# Structural page-scaffold tokens: an alt containing any of these as a WHOLE token is a
# template/layout label ("footer-logo", "wezom-starter-template"), not a business name.
_STRUCTURAL_ALT_TOKENS = {"logo", "лого", "footer", "header", "template", "starter",
                          "placeholder", "default", "icon", "menu", "nav"}
_ALT_TOKEN_RE = re.compile(r"[^0-9a-zA-Zа-яА-ЯіїєґІЇЄҐ]+")


def _extract_logo_alt(tree) -> str | None:
    for css in _LOGO_IMG_SELECTORS:
        for node in tree.css(css):
            alt = (node.attributes.get("alt") or "").strip()
            if not alt:
                continue
            low = alt.lower()
            if low in _GENERIC_ALTS:
                continue
            if {t for t in _ALT_TOKEN_RE.split(low) if t} & _STRUCTURAL_ALT_TOKENS:
                continue                                   # structural/template label
            return _cap_tagline(alt)
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

    def __init__(self, client: httpx.Client, store=None, throttle_sink=None):
        self._client = client
        self._store = store            # ValidatorStore: conditional GET (ETag/Last-Modified)
        self._throttle = throttle_sink  # (host, retry_after_seconds) -> None; 429/503 backoff

    def fetch(self, source: dict, last_seen_key: str | None):
        url = source["url_or_handle"]
        headers = {}
        if self._store is not None:
            v = self._store.get(url) or {}
            if v.get("etag"):
                headers["If-None-Match"] = v["etag"]
            if v.get("last_modified"):
                headers["If-Modified-Since"] = v["last_modified"]
        try:
            resp = self._client.get(url, follow_redirects=True, headers=headers or None)
            if resp.status_code in (429, 503) and self._throttle is not None:
                try:
                    secs = float(resp.headers.get("Retry-After", "") or 0.0)
                except ValueError:
                    secs = 0.0
                self._throttle(bare_host(url), secs)
                return [], last_seen_key
            if resp.status_code == 304:
                return [], last_seen_key            # незмінна сторінка — дешево
            resp.raise_for_status()
            if self._store is not None:
                self._store.put(url, resp.headers.get("ETag"),
                                resp.headers.get("Last-Modified"))

            tree = HTMLParser(resp.text)
            canonical = _extract_canonical(tree, url)
            image = _extract_image(tree, url)
            logo = _extract_logo(tree, url)
            logo_alt = _extract_logo_alt(tree)
            site_name = _extract_site_name(tree)
            site_tagline = _extract_site_tagline(tree)
            locality = _extract_locality(tree)
            has_offer = _has_offer_schema(tree)
            is_article = (_has_article_schema(tree) or _has_article_og(tree)
                          or _url_dated_permalink(url))
            has_business = _has_business_schema(tree)
            items: list[RawItem] = []
            seen_keys: set[str] = set()
            for node in tree.css(_BLOCK_SELECTOR):
                if self._has_block_descendant(node):
                    continue  # keep the innermost (leaf) block = one paragraph
                if self._under_chrome(node):
                    continue  # nav/header/footer/form is site chrome, never an offer
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
                                     image_url=image, logo_url=logo, logo_alt=logo_alt,
                                     site_name=site_name, site_tagline=site_tagline,
                                     locality=locality, has_offer_schema=has_offer,
                                     is_article=is_article,
                                     has_business_schema=has_business,
                                     canonical_url=canonical))
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
    def _under_chrome(node) -> bool:
        """True if `node` is nested inside site chrome (nav/header/footer/form)."""
        parent = node.parent
        while parent is not None:
            if parent.tag in _CHROME_TAGS:
                return True
            parent = parent.parent
        return False

    @staticmethod
    def _outermost_block(node):
        """Highest item-grouping ancestor of `node` (or `node` itself). Used to scope
        link capture up to the wrapping <article>/<li> only — NOT to generic layout
        <div>s, which would over-widen link capture to the whole page."""
        top = node
        parent = node.parent
        while parent is not None:
            if parent.tag in _LINK_SCOPE_TAGS:
                top = parent
            parent = parent.parent
        return top
