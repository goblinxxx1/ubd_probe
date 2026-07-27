"""Best-effort sitemap collector: walk sitemap-index -> child sitemaps -> <urlset>, decode
gzip, cap the number of documents fetched, and return de-duplicated page URLs. Any document
that fails to fetch or parse is skipped; the walk never raises."""

import gzip
import logging
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

# Product-catalog child sitemaps (WooCommerce `sitemap-pt-product-*`, `product-sitemap`, …)
# list only SKU pages, never promo/veteran landing pages — and they are huge. Skipping the
# download costs no promo coverage (their URLs never pass the promo filter anyway).
_SKIP_SITEMAP_SUBSTRINGS = ("product",)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # strip XML namespace


def _decode(resp) -> str:
    content = getattr(resp, "content", None)
    if isinstance(content, (bytes, bytearray)):
        if content[:2] == b"\x1f\x8b":
            try:
                return gzip.decompress(content).decode("utf-8", "replace")
            except OSError:
                return ""
        return content.decode("utf-8", "replace")
    return resp.text or ""


def collect_sitemap_urls(sitemap_urls, client, rate_limiter, domain, crawl_delay,
                         max_docs, skip_substrings=_SKIP_SITEMAP_SUBSTRINGS,
                         promo_filter=None, promo_target=0) -> list[str]:
    """Skip child sitemaps whose URL matches `skip_substrings` (product catalogs). If a
    `promo_filter` and positive `promo_target` are given, stop early once that many matching
    pages are collected — no more sitemap docs are downloaded once we have enough."""
    pages: list[str] = []
    seen_pages: set[str] = set()
    queue = list(sitemap_urls)
    visited: set[str] = set()
    fetched = 0
    promo_found = 0
    while queue and fetched < max_docs:
        sm = queue.pop(0)
        if sm in visited:
            continue
        visited.add(sm)
        fetched += 1
        try:
            rate_limiter.wait(domain, crawl_delay)
            resp = client.get(sm, follow_redirects=True)
            resp.raise_for_status()
            root = ET.fromstring(_decode(resp))
        except Exception as exc:  # noqa: BLE001 — skip a bad document, keep going
            log.warning("sitemap fetch/parse failed for %s: %s", sm, exc)
            continue
        is_index = _local(root.tag) == "sitemapindex"
        for loc in root.iter():
            if _local(loc.tag) != "loc" or not (loc.text and loc.text.strip()):
                continue
            value = loc.text.strip()
            if is_index:
                low = value.lower()
                if any(s in low for s in skip_substrings):
                    continue     # product-catalog sitemap: no promo pages, skip the giant download
                queue.append(value)
            elif value not in seen_pages:
                seen_pages.add(value)
                pages.append(value)
                if promo_filter is not None and promo_filter(value):
                    promo_found += 1
                    if promo_target and promo_found >= promo_target:
                        return pages     # enough promo pages — stop fetching further sitemaps
    return pages
