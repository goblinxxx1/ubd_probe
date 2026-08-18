"""Early domain-level language gate: judge a domain from its HOMEPAGE alone, so
DomainWalker can abandon a foreign-language site BEFORE enumerating its sitemap.
Complements the content gate (is_non_ukrainian) in _harvest_one, which only fires
after pages are fetched — by then the sitemap-walk budget is already spent.

Decisive signal is the homepage's Cyrillic ratio (is_non_ukrainian); hreflang only
vetoes the block when a Ukrainian (uk/ua) alternate exists. <html lang> is not used
as a verdict (sites misdeclare it). Any fetch/parse error or thin page → not foreign
(never block on uncertainty)."""

import logging

from selectolax.parser import HTMLParser

from crawler.util.text_lang import is_non_ukrainian

log = logging.getLogger(__name__)

_UA_HREFLANG = {"uk", "ua"}


def _hreflang_langs(tree) -> set[str]:
    langs: set[str] = set()
    for node in tree.css('link[rel="alternate"][hreflang]'):
        hl = (node.attributes.get("hreflang") or "").strip().lower()
        if hl:
            langs.add(hl.split("-", 1)[0])   # uk-UA -> uk
    return langs


class LanguageGate:
    def __init__(self, client, rate_limiter, *, min_ratio: float = 0.3,
                 min_alpha: int = 15):
        self._client = client
        self._rl = rate_limiter
        self._min_ratio = min_ratio
        self._min_alpha = min_alpha

    def is_foreign(self, homepage: str, domain: str, delay) -> bool:
        try:
            if self._rl is not None:
                self._rl.wait(domain, delay)
            resp = self._client.get(homepage, follow_redirects=True)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
        except Exception as exc:  # noqa: BLE001 — never block on uncertainty
            log.warning("language gate fetch failed for %s: %s", homepage, exc)
            return False
        if _UA_HREFLANG & _hreflang_langs(tree):
            return False                       # a Ukrainian version exists — keep
        body = tree.body
        text = body.text(separator=" ", strip=True) if body is not None else ""
        return is_non_ukrainian(text, min_ratio=self._min_ratio,
                                min_alpha=self._min_alpha)
