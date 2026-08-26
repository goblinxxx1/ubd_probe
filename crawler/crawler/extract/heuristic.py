import re
from urllib.parse import urlsplit

from crawler.dedup import content_hash
from crawler.discovery.providers import _normalize_url
from crawler.util.hosts import bare_host

_SOCIAL_HOSTS = ("facebook.com", "instagram.com", "t.me", "telegram.me",
                 "twitter.com", "x.com", "youtube.com", "youtu.be")


def _pick_target(links, source_url: str) -> str | None:
    src_host = bare_host(source_url)
    for raw in links or []:
        norm = _normalize_url(raw or "")
        if not norm:
            continue
        host = bare_host(norm)
        if not host or host == src_host:
            continue
        if any(host == s or host.endswith("." + s) for s in _SOCIAL_HOSTS):
            continue
        return norm
    return None


def _locations(locality: str | None, text: str) -> list[str]:
    names: list[str] = []
    if locality:
        resolved = find_cities(locality)
        names.extend(resolved if resolved else [locality.strip()])
    names.extend(find_cities(text))
    out, seen = [], set()
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    if not out and is_online(text):
        out = ["Онлайн"]
    return out


from crawler.discovery import promo_lexicon as pl
from crawler.discovery.geo import find_cities, is_online
from crawler.discovery.lexicon import classify, OFFER_LEXICON, TARGET_LEXICON
from crawler.extract.base import CategoryIndex
from crawler.models import OfferCandidate, RawItem

# Percent written as the symbol OR spelled out in Ukrainian ("20 відсотків", "15 проценти").
_PERCENT = re.compile(r"(\d{1,3})\s*(?:%|відсот\w*|процент\w*)")
_FIXED = re.compile(r"(\d[\d\s]{0,7})\s*(?:грн|гривень|₴|uah)", re.IGNORECASE)
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


def _discount_label(text: str, target_ids, categories) -> str | None:
    snippet = _title_from(text)
    if snippet and len(snippet) <= 80:
        return snippet
    names = [c["name"] for c in categories.target if c["id"] in set(target_ids)]
    return names[0] if names else None


def _has_audience_in_text(text: str) -> bool:
    """True iff a TARGET (audience) term appears in the block prose itself —
    not merely in provider/site_name metadata. Gates the loose FREE trigger."""
    return bool(classify(text or "", TARGET_LEXICON))


# About/info pages: their mission prose ("ми надаємо безкоштовну допомогу … ветеранам")
# trips the loose free-word signal though they carry no actual offer. Suppress FREE there;
# percent/fixed (which require a discount context) stay.
_INFO_PAGE_TOKENS = ("about", "pro-nas", "pro-proekt", "pro-kompani", "o-nas",
                     "o-kompani", "про-нас", "про-проєкт")


def _is_info_page(url) -> bool:
    return bool(url) and any(tok in url.lower() for tok in _INFO_PAGE_TOKENS)


class HeuristicExtractor:
    def __init__(self, require_discount: bool = False):
        self._require_discount = require_discount

    def extract(self, item: RawItem, provider: str,
                categories: CategoryIndex) -> OfferCandidate | None:
        text = item.text or ""
        low = text.lower()
        if not any(t in low for t in pl.offer_triggers()):
            return None
        if pl.INCREASE.search(low) and not pl.DISCOUNT_CTX.search(low):
            return None

        discount_type = None
        discount_value = None
        # A price reduction (percent/fixed) is the real discount and wins over «free»:
        # the same audience banner must not read as free on one page and percent on
        # another (that split blocks dedup against an already-published offer).
        if (m := _PERCENT.search(text)) and pl.DISCOUNT_CTX.search(low):
            discount_type, discount_value = "percent", m.group(1)
        elif (m := _FIXED.search(text)) and pl.DISCOUNT_CTX.search(low) \
                and not pl.PRICE_RANGE.search(low):
            # A catalog "від X ₴ до Y ₴" span is not a fixed discount — skip it.
            discount_type, discount_value = "fixed", re.sub(r"\s", "", m.group(1))
        elif (pl.FREE.search(pl.FREE_SERVICE.sub(" ", low)) and _has_audience_in_text(text)
              and not _is_info_page(item.url)):
            # FREE only when it's not merely a complementary free service (consultation/
            # delivery, masked out above) and not an about/info page (mission text trips
            # the weak free-word signal without a real offer).
            discount_type = "free"

        if self._require_discount and discount_type is None:
            return None

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

        blob = f"{provider} {item.site_name or ''} {text}".lower()
        target_slugs = {slug for _, slug in classify(blob, TARGET_LEXICON)}
        if not target_slugs:
            return None
        target_ids = [c["id"] for c in categories.target if c["slug"] in target_slugs]
        offer_matches = classify(blob, OFFER_LEXICON)

        promo_title = _title_from(text)
        title = (item.site_tagline or "").strip() or promo_title
        discounts = ([{"label": _discount_label(text, target_ids, categories),
                       "discount_type": discount_type,
                       "discount_value": discount_value}]
                     if discount_type is not None else [])
        display_provider = ((item.logo_alt or item.site_name or "").strip()
                             or provider)
        return OfferCandidate(
            source_id=item.source_id,
            title=title,
            provider=display_provider,
            body=text,
            locations=_locations(item.locality, text),
            offer_type="discount",
            discount_type=discount_type,
            discount_value=discount_value,
            valid_until=valid_until,
            content_hash=content_hash(promo_title, provider, text),
            site_url=(f"{urlsplit(item.url).scheme}://{urlsplit(item.url).netloc}"
                      if item.url else None),
            # canonical > сира url — сайт сам згортає utm/фасети/пагінацію в одну
            # ідентичність сторінки, тому дедуп бачить той самий офер.
            article_url=(item.canonical_url or item.url),
            image_url=getattr(item, "image_url", None),
            logo_url=getattr(item, "logo_url", None),
            target_url=_pick_target(getattr(item, "links", None), item.url or ""),
            target_category_ids=target_ids,
            offer_category_matches=offer_matches,
            discounts=discounts,
        )
