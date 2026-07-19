import re
from urllib.parse import urlsplit

from crawler.dedup import content_hash
from crawler.discovery.providers import _normalize_url

_SOCIAL_HOSTS = ("facebook.com", "instagram.com", "t.me", "telegram.me",
                 "twitter.com", "x.com", "youtube.com", "youtu.be")


def _pick_target(links, source_url: str) -> str | None:
    src_host = urlsplit(source_url or "").netloc.lower().removeprefix("www.")
    for raw in links or []:
        norm = _normalize_url(raw or "")
        if not norm:
            continue
        host = urlsplit(norm).netloc.lower().removeprefix("www.")
        if not host or host == src_host:
            continue
        if any(host == s or host.endswith("." + s) for s in _SOCIAL_HOSTS):
            continue
        return norm
    return None
from crawler.discovery.geo import find_city, is_online
from crawler.extract.base import CategoryIndex
from crawler.models import OfferCandidate, RawItem

# Any of these signals that the text is an offer at all.
_OFFER_TRIGGERS = (
    "знижк", "акці", "промокод", "безкоштов", "безплатн", "%", "діє до",
    "спецпропоз", "розпродаж",
)
_PERCENT = re.compile(r"(\d{1,3})\s*%")
_FIXED = re.compile(r"(\d[\d\s]{0,7})\s*(?:грн|₴|uah)", re.IGNORECASE)
_FREE = re.compile(r"безкоштов|безплатн|\bfree\b", re.IGNORECASE)
_UNTIL = re.compile(r"(?:до|діє до)\s+(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?")


_SENT_END = re.compile(r"(?<=[.!?…])\s")


def _title_from(text: str) -> str:
    t = text.strip()
    if not t:
        return t
    first = t.splitlines()[0]
    m = _SENT_END.search(first)
    if m:
        first = first[:m.start() + 1]
    if len(first) > 80:
        first = first[:80].rsplit(" ", 1)[0] or first[:80]
    return first.strip()


def _match_categories(text_low: str, cats: list[dict]) -> list[int]:
    ids = []
    for c in cats:
        needle = c["name"].lower()[:5]  # match on stem to survive Ukrainian inflection
        if needle and needle in text_low:
            ids.append(c["id"])
    return ids


class HeuristicExtractor:
    def extract(self, item: RawItem, provider: str,
                categories: CategoryIndex) -> OfferCandidate | None:
        text = item.text or ""
        low = text.lower()
        if not any(t in low for t in _OFFER_TRIGGERS):
            return None

        discount_type = None
        discount_value = None
        if _FREE.search(low):
            discount_type = "free"
        elif (m := _PERCENT.search(text)):
            discount_type, discount_value = "percent", m.group(1)
        elif (m := _FIXED.search(text)):
            discount_type, discount_value = "fixed", re.sub(r"\s", "", m.group(1))

        valid_until = None
        if (m := _UNTIL.search(low)):
            from datetime import date
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else date.today().year
            if year < 100:
                year += 2000
            try:
                valid_until = date(year, month, day)
            except ValueError:
                valid_until = None

        title = _title_from(text)
        return OfferCandidate(
            source_id=item.source_id,
            title=title,
            provider=provider,
            body=text,
            location=item.locality or find_city(text) or ("Онлайн" if is_online(text) else None),
            offer_type="discount",
            discount_type=discount_type,
            discount_value=discount_value,
            valid_until=valid_until,
            content_hash=content_hash(title, provider, text),
            site_url=(f"{urlsplit(item.url).scheme}://{urlsplit(item.url).netloc}"
                      if item.url else None),
            article_url=item.url,
            image_url=getattr(item, "logo_url", None),
            target_url=_pick_target(getattr(item, "links", None), item.url or ""),
            target_category_ids=_match_categories(low, categories.target),
            offer_category_ids=_match_categories(low, categories.offer),
        )
