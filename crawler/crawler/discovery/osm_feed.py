"""DDG-independent domain auto-fill: enumerate Ukrainian branded POIs with websites from
OpenStreetMap/Overpass and emit their domains as website candidates. Mirrors brand_feed —
Overpass is touched only on a rare refresh; passes read the cache offline."""

import logging
import time
from collections import Counter, defaultdict

import httpx

from crawler.discovery.blocklist import is_blocked_host
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate
from crawler.util.hosts import bare_host

log = logging.getLogger(__name__)

_OSM_UA = "UBDCrawler/0.1 (+https://ubd.example; osm domain enumerator)"

# UA branded POIs that carry a website — chains, not one-off shops.
_OVERPASS_QUERY = (
    "[out:json][timeout:180];"
    'area["ISO3166-1"="UA"][admin_level=2]->.ua;'
    '(nwr(area.ua)["brand"]["website"];'
    'nwr(area.ua)["brand"]["contact:website"];);'
    "out tags 20000;"
)


class OsmEnumerator:
    """Best-effort brand→host enumeration via one Overpass query. HTTP is injected for tests;
    every failure path returns an empty map so the caller keeps the previous cache."""

    def __init__(self, overpass_url, timeout=25.0, min_pois=2, max_domains=500,
                 client_factory=None, sleep=None, min_delay=1.0):
        self._overpass = overpass_url
        self._min_pois = min_pois
        self._max_domains = max_domains
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=timeout, headers={"User-Agent": _OSM_UA}))
        self._sleep = sleep or time.sleep
        self._delay = min_delay

    def enumerate(self) -> dict[str, str]:
        by_brand: dict[str, Counter] = defaultdict(Counter)
        for el in self._query():
            tags = el.get("tags", {})
            brand = (tags.get("brand") or "").strip()
            host = bare_host(tags.get("website") or tags.get("contact:website") or "")
            if brand and host:
                by_brand[brand][host] += 1
        # best host per brand, filtered by min POI count and blocklist
        picked: dict[str, str] = {}
        for brand, hosts in by_brand.items():
            host, count = hosts.most_common(1)[0]
            if count >= self._min_pois and not is_blocked_host(host):
                picked[brand] = host
        # dedup by host (stable brand order), cap
        seen: set[str] = set()
        out: dict[str, str] = {}
        for brand in sorted(picked):
            host = picked[brand]
            if host in seen:
                continue
            seen.add(host)
            out[brand] = host
            if len(out) >= self._max_domains:
                break
        return out

    def _query(self) -> list:
        try:
            if self._delay:
                self._sleep(self._delay)
            with self._client_factory() as client:
                resp = client.post(self._overpass, data={"data": _OVERPASS_QUERY})
                resp.raise_for_status()
                data = resp.json()
            return data.get("elements", []) or []
        except Exception as exc:  # noqa: BLE001 — enumeration best-effort
            log.warning("osm enumeration query failed: %s", exc)
            return []


class OsmDomainFeed:
    """Offline emitter: a rotating window of website SourceCandidates from the OSM cache,
    advancing the cache's persisted cursor each pass so the whole set is covered over passes."""

    def __init__(self, cache, per_pass=20):
        self._cache = cache
        self._per_pass = per_pass

    def candidates(self, known: set[str]) -> list[SourceCandidate]:
        brands = sorted(self._cache.domains())
        size = len(brands)
        if size == 0:
            return []
        n = max(1, min(int(self._per_pass), size))
        cursor = self._cache.cursor()
        if cursor < 0 or cursor >= size:
            cursor = 0
        window = [brands[(cursor + i) % size] for i in range(n)]
        self._cache.set_cursor((cursor + n) % size)
        domains = self._cache.domains()
        out: list[SourceCandidate] = []
        for brand in window:
            host = domains.get(brand)
            if not host:
                continue
            url = f"https://{host}"
            if normalize_ref("website", url) in known:
                continue
            out.append(SourceCandidate(
                name=brand, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"osm-feed:{host}"))
        return out
