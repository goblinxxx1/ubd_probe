"""Ізольований «підпошук»: з каталог-сторінки (myhelp-тип) дістати назву бізнесу,
ОДИН РАЗ пошукати його офіційний сайт і витягти реальний офер уже звідти. Повна
ізоляція від основного краулу — не пише в domain_registry/aggregator_store/джерела."""

import logging
from urllib.parse import urlsplit

from crawler.discovery.blocklist import is_blocked_host
from crawler.discovery.host_quality import (_DIR_CONTAINER, DIRECTORY_HOST_SEEDS,
                                             is_low_value_host, is_news_host)
from crawler.util.hosts import bare_host, is_foreign_host, is_ru_by_geo

log = logging.getLogger(__name__)


def extract_business(items, cand) -> tuple[str | None, str | None]:
    """(name, city) з каталог-сторінки. name — де-слаг бізнес-сегмента URL (чисте,
    надійне джерело для пошуку); city — locality першого item, інакше None."""
    url = (getattr(cand, "url_or_handle", None)
           or next((it.url for it in items if getattr(it, "url", None)), None))
    parts = [p for p in urlsplit(url or "").path.split("/") if p]
    name = None
    for i, seg in enumerate(parts):
        if seg.lower() in _DIR_CONTAINER and i + 1 < len(parts):
            name = parts[i + 1].replace("-", " ").replace("_", " ").strip().lower()
            break
    city = next((it.locality for it in items if getattr(it, "locality", None)), None)
    return (name or None), city


_SOCIAL = frozenset({"facebook.com", "instagram.com", "t.me", "tiktok.com",
                     "youtube.com", "twitter.com", "x.com", "linkedin.com"})


def _rejected_host(h: str) -> bool:
    if not h or "." not in h:
        return True
    if h in DIRECTORY_HOST_SEEDS or h in _SOCIAL:
        return True
    if any(h == s or h.endswith("." + s) for s in _SOCIAL):
        return True
    url = "https://" + h
    return (is_blocked_host(h) or is_foreign_host(url) or is_ru_by_geo(url)
            or is_low_value_host(h) or is_news_host(h))


def resolve_business_site(name, city, search) -> str | None:
    """ОДИН пошук `"<name>" <city>` → перший чистий UA-бізнес-хост, інакше None.
    R1: для генеричної назви (≤2 токени) без міста — None (не вгадуємо навмання)."""
    if not name:
        return None
    tokens = [t for t in name.split() if len(t) > 1]
    if len(tokens) <= 2 and not city:
        return None                                  # R1: homonym guard
    keyword = f'"{name}" {city}' if city else f'"{name}"'
    try:
        results = search(keyword)
    except Exception as exc:  # noqa: BLE001 — search is best-effort
        log.warning("subsearch resolve failed for %r: %s", name, exc)
        return None
    for cand in results or []:
        if getattr(cand, "type", None) != "website":
            continue
        h = bare_host(getattr(cand, "url_or_handle", None))
        if not _rejected_host(h):
            return h
    return None
