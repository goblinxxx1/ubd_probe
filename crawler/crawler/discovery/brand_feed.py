"""Offline curated brand→domain feed: resolve known brands to official domains via a
rare OSM/Wikidata refresh, cache them, and emit website SourceCandidates each pass.

Curated core (same technique as query_grid.py/geo.py): the brand set IS
query_grid.BRANDS; BRAND_SEEDS adds an optional Wikidata QID (fast-path hint) and a
required fallback domain per brand. The network (Wikidata/Overpass) is touched only
during refresh; passes read the cache offline."""

import copy
import json
import logging
import os
import time
from collections import Counter
from urllib.parse import urlparse

import httpx

from crawler.discovery.query_grid import BRANDS  # noqa: F401 — referenced by the seeds invariant
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate

log = logging.getLogger(__name__)

# brand -> (wikidata_qid | None, fallback_domain)
# Fallback domains are best-effort BOOTSTRAP values: they seed the feed before any
# successful refresh and are overwritten by authoritative Wikidata/Overpass data on
# refresh. QID is an optional hint; when None the resolver discovers the brand's
# wikidata id / website via Overpass at refresh time.
BRAND_SEEDS: dict[str, tuple[str | None, str]] = {
    "Rozetka": (None, "rozetka.com.ua"),
    "Comfy": (None, "comfy.ua"),
    "Фокстрот": (None, "foxtrot.com.ua"),
    "Епіцентр": (None, "epicentrk.ua"),
    "Нова Лінія": (None, "novalinia.ua"),
    "JYSK": (None, "jysk.ua"),
    "EVA": (None, "eva.ua"),
    "Prostor": (None, "prostor.ua"),
    "Аврора": (None, "aurora.ua"),
    "Копійочка": (None, "kopiyochka.ua"),
    "Сільпо": (None, "silpo.ua"),
    "АТБ": (None, "atbmarket.com"),
    "Novus": (None, "novus.online"),
    "VARUS": (None, "varus.ua"),
    "Metro": (None, "metro.ua"),
    "OKKO": (None, "okko.ua"),
    "WOG": (None, "wog.ua"),
    "UPG": (None, "upg.ua"),
    "SOCAR": (None, "socar.ua"),
    "БРСМ": (None, "brsm-nafta.com"),
    "KLO": (None, "klo.ua"),
    "Parallel": (None, "parallel.ua"),
    "Подорожник": (None, "podorozhnyk.ua"),
    "АНЦ": (None, "anc.ua"),
    "Бажаємо здоров'я": (None, "apteka-bz.com.ua"),
    "Аптека Доброго Дня": (None, "add.ua"),
    "Алло": (None, "allo.ua"),
    "Цитрус": (None, "ctrs.com.ua"),
    "MOYO": (None, "moyo.ua"),
    "Brain": (None, "brain.com.ua"),
    "Eldorado": (None, "eldorado.ua"),
    "INTERTOP": (None, "intertop.ua"),
    "Colin's": (None, "colins.ua"),
    "LC Waikiki": (None, "lcwaikiki.ua"),
    "Adidas": (None, "adidas.ua"),
    "Puma": (None, "ua.puma.com"),
    "New Balance": (None, "newbalance.ua"),
    "Megasport": (None, "megasport.ua"),
    "ПриватБанк": (None, "privatbank.ua"),
    "monobank": (None, "monobank.ua"),
    "Ощадбанк": (None, "oschadbank.ua"),
    "ПУМБ": (None, "pumb.ua"),
    "Sense Bank": (None, "sensebank.com.ua"),
    "Райффайзен Банк": (None, "raiffeisen.ua"),
    "Нова пошта": (None, "novaposhta.ua"),
    "Київстар": (None, "kyivstar.ua"),
    "Vodafone": (None, "vodafone.ua"),
    "lifecell": (None, "lifecell.ua"),
}

_EMPTY_CACHE = {"version": 1, "refreshed_at": 0.0, "domains": {}, "cursor": 0}


class BrandDomainCache:
    """Persistent JSON brand→domain map with a refresh-freshness gate. Atomic writes."""

    def __init__(self, path: str, data: dict | None = None, clock=time.time):
        self._path = path
        self._clock = clock
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY_CACHE))

    @classmethod
    def load(cls, path: str, clock=time.time) -> "BrandDomainCache":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("brand cache must be a JSON object")
            for k, default in _EMPTY_CACHE.items():
                data.setdefault(k, copy.deepcopy(default))
        except (OSError, ValueError) as exc:
            log.warning("brand cache load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data, clock=clock)

    def is_stale(self, ttl_seconds: float) -> bool:
        return self._clock() - float(self._data.get("refreshed_at", 0.0)) >= ttl_seconds

    def domains(self) -> dict[str, str]:
        return dict(self._data.get("domains", {}))

    def cursor(self) -> int:
        return int(self._data.get("cursor", 0))

    def set_cursor(self, value: int) -> None:
        self._data["cursor"] = int(value)
        self._save()

    def replace(self, domains: dict[str, str]) -> None:
        self._data["domains"] = dict(domains)
        self._data["refreshed_at"] = self._clock()
        self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)


DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_WIKIDATA_URL = "https://www.wikidata.org/w/api.php"
_RESOLVER_UA = "UBDCrawler/0.1 (+https://ubd.example; brand-domain resolver)"


def _host(url: str) -> str | None:
    """Bare registrable host: strip scheme, userinfo, port, path, and a leading www."""
    if not url or not url.strip():
        return None
    raw = url.strip()
    if "//" not in raw:
        raw = "//" + raw
    netloc = urlparse(raw).netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


class BrandResolver:
    """Best-effort brand→domain resolution via Wikidata P856 and Overpass website tags.
    HTTP is injected for testability; every failure path returns None."""

    def __init__(self, client_factory=None, overpass_url=DEFAULT_OVERPASS_URL,
                 wikidata_url=DEFAULT_WIKIDATA_URL, timeout=25.0,
                 sleep=time.sleep, min_delay=1.0):
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=timeout, headers={"User-Agent": _RESOLVER_UA}))
        self._overpass = overpass_url
        self._wikidata = wikidata_url
        self._sleep = sleep
        self._delay = min_delay

    def resolve(self, brand: str, qid: str | None = None) -> str | None:
        if qid:
            host = self._wikidata_site(qid)
            if host:
                return host
        tags = self._overpass_tags(brand)
        if tags.get("wikidata"):
            host = self._wikidata_site(tags["wikidata"])
            if host:
                return host
        hosts = [h for h in (_host(w) for w in tags.get("websites", [])) if h]
        if hosts:
            return Counter(hosts).most_common(1)[0][0]
        return None

    def _wikidata_site(self, qid: str) -> str | None:
        try:
            if self._delay:
                self._sleep(self._delay)
            with self._client_factory() as client:
                resp = client.get(self._wikidata, params={
                    "action": "wbgetclaims", "entity": qid,
                    "property": "P856", "format": "json"})
                resp.raise_for_status()
                data = resp.json()
            for claim in data.get("claims", {}).get("P856", []):
                value = (claim.get("mainsnak", {}).get("datavalue", {}) or {}).get("value")
                host = _host(value) if isinstance(value, str) else None
                if host:
                    return host
        except Exception as exc:  # noqa: BLE001 — resolution is best-effort
            log.warning("wikidata P856 failed for %s: %s", qid, exc)
        return None

    def _overpass_tags(self, brand: str) -> dict:
        query = f'[out:json][timeout:25];nwr["brand"="{brand}"];out tags 50;'
        try:
            if self._delay:
                self._sleep(self._delay)
            with self._client_factory() as client:
                resp = client.post(self._overpass, data={"data": query})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — resolution is best-effort
            log.warning("overpass failed for %r: %s", brand, exc)
            return {}
        wikidata = None
        websites: list[str] = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            wikidata = wikidata or tags.get("brand:wikidata") or tags.get("wikidata")
            for key in ("website", "contact:website"):
                if tags.get(key):
                    websites.append(tags[key])
        return {"wikidata": wikidata, "websites": websites}


def refresh_brand_domains(cache: "BrandDomainCache", resolver, seeds=BRAND_SEEDS) -> None:
    """Resolve every seed brand to a domain (best-effort), falling back to the curated
    seed domain, and persist the result to the cache."""
    resolved: dict[str, str] = {}
    for brand, (qid, fallback) in seeds.items():
        domain = None
        try:
            domain = resolver.resolve(brand, qid)
        except Exception as exc:  # noqa: BLE001 — one brand must not kill the batch
            log.warning("brand resolve failed for %s: %s", brand, exc)
            domain = None
        resolved[brand] = domain or fallback
    cache.replace(resolved)


class BrandFeed:
    """Offline emitter: a rotating window of website SourceCandidates from the
    cache/fallback. The window advances a persisted cursor each pass so every brand
    (including ones added as the curated set grows) is covered over successive passes."""

    def __init__(self, cache: "BrandDomainCache", seeds=BRAND_SEEDS, per_pass=20):
        self._cache = cache
        self._seeds = seeds
        self._per_pass = per_pass

    def candidates(self, known: set[str]) -> list[SourceCandidate]:
        brands = list(self._seeds)
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
            domain = domains.get(brand) or self._seeds[brand][1]
            url = f"https://{domain}"
            if normalize_ref("website", url) in known:
                continue
            out.append(SourceCandidate(
                name=brand, type="website", url_or_handle=url,
                discovered_from_source_id=None,
                discovery_note=f"brand-feed:{brand}"))
        return out
