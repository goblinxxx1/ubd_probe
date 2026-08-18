"""Domain-depth expansion: turn a website homepage candidate into a small set of
promo-relevant page URLs (robots + sitemap + BFS fallback) under a per-domain politeness
layer. This module hosts the promo-URL filter and the DomainWalker orchestrator."""

import logging
from dataclasses import dataclass
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from crawler.discovery.passive import normalize_ref
from crawler.discovery.promo_lexicon import (  # re-export url_is_promo for callers/tests
    is_excluded, page_is_target, seed_is_target, url_is_promo)
from crawler.discovery.sitemap import collect_sitemap_urls
from crawler.util.hosts import bare_host, is_ru_by_geo

log = logging.getLogger(__name__)


def _host(url: str) -> str:
    return bare_host(url)


def _same_domain(url: str, domain: str) -> bool:
    h = _host(url)
    return h == domain or h.endswith("." + domain)


@dataclass
class WalkPlan:
    domain: str
    urls: list[str]
    crawl_delay: float | None
    foreign: bool = False


class DomainWalker:
    def __init__(self, client, robots, rate_limiter, *, domain_page_cap=10,
                 sitemap_max_docs=20, bfs_max_depth=2, bfs_max_pages=8,
                 bfs_trigger_min=3, domain_min_delay=3.0, crawl_delay_cap=30.0,
                 language_gate=None):
        self._client = client
        self._robots = robots
        self._rl = rate_limiter
        self._page_cap = domain_page_cap
        self._sitemap_max_docs = sitemap_max_docs
        self._bfs_max_depth = bfs_max_depth
        self._bfs_max_pages = bfs_max_pages
        self._bfs_trigger_min = bfs_trigger_min
        self._floor = domain_min_delay
        self._cap = crawl_delay_cap
        # Collect a wider candidate pool than we fetch, so promo/offer pages can be sorted
        # ahead of generic page-type targets BEFORE the page_cap is applied (a site can list
        # dozens of info pages before its offer pages in sitemap order).
        self._collect_cap = max(domain_page_cap * 6, 60)
        self._lang_gate = language_gate

    def walk(self, cand) -> WalkPlan:
        homepage = cand.url_or_handle
        domain = _host(homepage)
        try:
            robots = self._robots.get(domain)
            delay = min(max(self._floor, robots.crawl_delay() or 0.0), self._cap)
            if self._lang_gate is not None and self._lang_gate.is_foreign(
                    homepage, domain, delay):
                return WalkPlan(domain, [], delay, foreign=True)
            sm_urls = robots.sitemaps() or [f"https://{domain}/sitemap.xml"]
            found = collect_sitemap_urls(
                sm_urls, self._client, self._rl, domain, delay, self._sitemap_max_docs,
                promo_filter=lambda u: _same_domain(u, domain) and page_is_target(u),
                promo_target=self._collect_cap)
            promo = [u for u in found if _same_domain(u, domain) and page_is_target(u)]
            if len(promo) < self._bfs_trigger_min:
                promo += self._bfs(homepage, domain, robots, delay)
            # Offer/promo-slug pages (SEED_URL_TOKENS: offers/akcii/discount/…) ahead of
            # generic page-type targets (about/contacts/faq) so the page_cap budget buys
            # real offer pages, not filler. Stable sort preserves sitemap order within a tier.
            promo.sort(key=lambda u: 0 if url_is_promo(u) else 1)
            urls = self._finalize(homepage, promo, robots)
            return WalkPlan(domain, urls, delay)
        except Exception as exc:  # noqa: BLE001 — expansion must never crash a pass
            log.warning("domain walk failed for %s: %s", homepage, exc)
            return WalkPlan(domain, [homepage], self._floor)

    def _finalize(self, homepage, promo, robots) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for url in [homepage, *promo]:
            if url == homepage and not seed_is_target(homepage):
                continue                                # active non-target candidate: skip seed
            if is_ru_by_geo(url):
                continue                                # RU/BY page (e.g. /spb) — never fetch
            if not robots.can_fetch(url):
                continue
            key = normalize_ref("website", url)
            if key in seen:
                continue
            seen.add(key)
            out.append(url)
            if len(out) >= self._page_cap:
                break
        return out

    def _bfs(self, homepage, domain, robots, delay) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        frontier = [homepage]
        fetched = 0
        for _ in range(self._bfs_max_depth):
            nxt: list[str] = []
            for page in frontier:
                if fetched >= self._bfs_max_pages:
                    return found
                if not robots.can_fetch(page):
                    continue
                fetched += 1
                for link, anchor in self._links(page, domain, delay):
                    if link in seen:
                        continue
                    seen.add(link)
                    if is_excluded(link) or is_ru_by_geo(link):
                        continue                        # hard skip: no collect, no traverse
                    if page_is_target(link, anchor):
                        found.append(link)
                    else:
                        nxt.append(link)                # neutral -> traverse deeper
            frontier = nxt
        return found

    def _links(self, url, domain, delay) -> list[tuple[str, str]]:
        try:
            self._rl.wait(domain, delay)
            resp = self._client.get(url, follow_redirects=True)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
        except Exception as exc:  # noqa: BLE001 — one page failing must not stop BFS
            log.warning("bfs link fetch failed for %s: %s", url, exc)
            return []
        out: list[tuple[str, str]] = []
        for a in tree.css("a"):
            href = a.attributes.get("href")
            if not href:
                continue
            absolute = urljoin(url, href)
            if _same_domain(absolute, domain):
                out.append((absolute.split("#")[0], a.text() or ""))
        return out
