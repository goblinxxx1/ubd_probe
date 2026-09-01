"""Ізольований «підпошук»: з каталог-сторінки (myhelp-тип) дістати назву бізнесу,
ОДИН РАЗ пошукати його офіційний сайт і витягти реальний офер уже звідти. Повна
ізоляція від основного краулу — не пише в domain_registry/aggregator_store/джерела."""

import logging
from urllib.parse import urlsplit

from crawler.discovery.host_quality import _DIR_CONTAINER

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
