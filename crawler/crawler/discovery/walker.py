"""Domain-depth expansion: turn a website homepage candidate into a small set of
promo-relevant page URLs (robots + sitemap + BFS fallback) under a per-domain politeness
layer. This module hosts the promo-URL filter and the DomainWalker orchestrator."""

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser

from crawler.discovery.passive import normalize_ref
from crawler.discovery.promo_lexicon import url_is_promo  # re-export for callers
from crawler.discovery.sitemap import collect_sitemap_urls

log = logging.getLogger(__name__)


def _host(url: str) -> str:
    netloc = urlsplit(url or "").netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


def _same_domain(url: str, domain: str) -> bool:
    h = _host(url)
    return h == domain or h.endswith("." + domain)


@dataclass
class WalkPlan:
    domain: str
    urls: list[str]
    crawl_delay: float | None


class DomainWalker:
    def __init__(self, client, robots, rate_limiter, *, domain_page_cap=10,
                 sitemap_max_docs=20, bfs_max_depth=2, bfs_max_pages=8,
                 bfs_trigger_min=3, domain_min_delay=3.0, crawl_delay_cap=30.0):
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

    def walk(self, cand) -> WalkPlan:
        homepage = cand.url_or_handle
        domain = _host(homepage)
        try:
            robots = self._robots.get(domain)
            delay = min(max(self._floor, robots.crawl_delay() or 0.0), self._cap)
            sm_urls = robots.sitemaps() or [f"https://{domain}/sitemap.xml"]
            found = collect_sitemap_urls(sm_urls, self._client, self._rl, domain,
                                         delay, self._sitemap_max_docs)
            promo = [u for u in found if _same_domain(u, domain) and url_is_promo(u)]
            if len(promo) < self._bfs_trigger_min:
                promo += self._bfs(homepage, domain, robots, delay)
            urls = self._finalize(homepage, promo, robots)
            return WalkPlan(domain, urls, delay)
        except Exception as exc:  # noqa: BLE001 — expansion must never crash a pass
            log.warning("domain walk failed for %s: %s", homepage, exc)
            return WalkPlan(domain, [homepage], self._floor)

    def _finalize(self, homepage, promo, robots) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for url in [homepage, *promo]:
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
                for link in self._links(page, domain, delay):
                    if link in seen:
                        continue
                    seen.add(link)
                    if url_is_promo(link):
                        found.append(link)
                    else:
                        nxt.append(link)
            frontier = nxt
        return found

    def _links(self, url, domain, delay) -> list[str]:
        try:
            self._rl.wait(domain, delay)
            resp = self._client.get(url, follow_redirects=True)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
        except Exception as exc:  # noqa: BLE001 — one page failing must not stop BFS
            log.warning("bfs link fetch failed for %s: %s", url, exc)
            return []
        out: list[str] = []
        for a in tree.css("a"):
            href = a.attributes.get("href")
            if not href:
                continue
            absolute = urljoin(url, href)
            if _same_domain(absolute, domain):
                out.append(absolute.split("#")[0])
        return out
