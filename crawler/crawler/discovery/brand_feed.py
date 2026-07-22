"""Offline curated brand→domain feed: resolve known brands to official domains via a
rare OSM/Wikidata refresh, cache them, and emit website SourceCandidates each pass.

Curated core (same technique as query_grid.py/geo.py): the brand set IS
query_grid.BRANDS; BRAND_SEEDS adds an optional Wikidata QID (fast-path hint) and a
required fallback domain per brand. The network (Wikidata/Overpass) is touched only
during refresh; passes read the cache offline."""

from crawler.discovery.query_grid import BRANDS  # noqa: F401 — referenced by the seeds invariant

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
