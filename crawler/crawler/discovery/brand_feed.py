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

from crawler.discovery.query_grid import BRANDS  # noqa: F401 — referenced by the seeds invariant

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

_EMPTY_CACHE = {"version": 1, "refreshed_at": 0.0, "domains": {}}


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
