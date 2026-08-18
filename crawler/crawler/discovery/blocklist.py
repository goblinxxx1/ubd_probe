"""Hosts that must never be attributed as offer providers or offer sources:
news media, government, stock-photo banks, social-video aggregators."""

import re

from crawler.util.hosts import bare_host

_MEDIA = {
    "nv.ua", "24tv.ua", "061.ua", "pravda.com.ua", "unian.ua", "tsn.ua",
    "rbc.ua", "censor.net", "obozrevatel.com", "segodnya.ua",
    # observed leaks from live active-search runs (news/blogs, not providers)
    "ukr.net", "dnipro.media", "fakty.com.ua", "blog.ipay.ua",
    # aggregators/portals/NGO write-ups — not the actual provider of the discount
    "veteranam.info", "engage.org.ua", "goncharenkocentre.com.ua",
    # global business-directory aggregator (per-business listing pages carry the
    # listed business's schema, so the behavioural media-autoblock never fires)
    "findglocal.com",
    # curated UA news/media that leaked as "productive" providers (Track A)
    "znaj.ua", "ukrainianwall.com", "kosht.media", "epravda.com.ua",
    "protocol.ua", "focus.ua", "glavcom.ua", "thepage.ua", "parlament.ua",
    "kharakter.media",
    # well-known national news outlets (curated, confident — not businesses)
    "liga.net", "hromadske.ua", "suspilne.media", "ukrinform.ua",
    "korrespondent.net", "gordonua.com", "lb.ua", "zaxid.net",
    # regional news outlets whose permalinks (numeric ids, not /YYYY/MM/) and
    # missing og:type=article slip past the auto media-gate — curated by host
    "dumka.media",
}
_STOCK = {"depositphotos.com", "shutterstock.com", "istockphoto.com", "freepik.com"}
_SOCIAL = {
    "tiktok.com", "youtube.com", "youtu.be", "pinterest.com",
    "twitter.com", "x.com",
}
_BLOCKED = _MEDIA | _STOCK | _SOCIAL

_LEARNED: frozenset[str] = frozenset()

# Hosts pinned as Russia/Belarus by a geo signal in the URL (path/subdomain) —
# persisted crawler-side (GeoBlockStore) and pushed here so the WHOLE host is never
# fetched/walked/re-fed again. Kept separate from _LEARNED (media/aggregator audit).
_GEO_BLOCKED: frozenset[str] = frozenset()

# Hosts pinned as non-Ukrainian by the language gate (homepage content + hreflang) —
# persisted crawler-side (LangBlockStore) and pushed here so the WHOLE host is never
# fetched/walked/re-fed again. Separate slot from _GEO_BLOCKED and _LEARNED.
_LANG_BLOCKED: frozenset[str] = frozenset()


def reload_lang_blocked(hosts) -> None:
    """Replace the language-blocked host set. None/empty ⇒ cleared."""
    global _LANG_BLOCKED
    if not hosts:
        _LANG_BLOCKED = frozenset()
        return
    norm = {bare_host(h) for h in hosts if h and h.strip()}
    _LANG_BLOCKED = frozenset(n for n in norm if n)


def reload_learned(hosts) -> None:
    """Replace the learned media/aggregator host set (approved via the Vue audit).
    None/empty ⇒ SEED-only, byte-equivalent to prior behaviour."""
    global _LEARNED
    if not hosts:
        _LEARNED = frozenset()
        return
    norm = {bare_host(h) for h in hosts if h and h.strip()}
    _LEARNED = frozenset(n for n in norm if n)


def add_learned(host) -> None:
    """Incrementally union one host into the runtime learned set, so is_blocked_host
    drops it immediately within the current run (persistence is backend-side)."""
    global _LEARNED
    h = bare_host(host) if host and host.strip() else ""
    if h:
        _LEARNED = _LEARNED | frozenset({h})


def reload_geo_blocked(hosts) -> None:
    """Replace the RU/BY geo-blocked host set. None/empty ⇒ cleared."""
    global _GEO_BLOCKED
    if not hosts:
        _GEO_BLOCKED = frozenset()
        return
    norm = {bare_host(h) for h in hosts if h and h.strip()}
    _GEO_BLOCKED = frozenset(n for n in norm if n)


def is_blocked_host(host: str | None) -> bool:
    if not host:
        return False
    host = bare_host(host)
    if not host:
        return False
    if host == "gov.ua" or host.endswith(".gov.ua"):
        return True
    if any(host == d or host.endswith("." + d) for d in _BLOCKED):
        return True
    if any(host == d or host.endswith("." + d) for d in _GEO_BLOCKED):
        return True
    if any(host == d or host.endswith("." + d) for d in _LANG_BLOCKED):
        return True
    return any(host == d or host.endswith("." + d) for d in _LEARNED)


_TELEGRAM_HANDLES = {"nau_info"}

# Strong, unambiguous news/info-channel markers — substring match is safe.
_CHANNEL_NEWS_STRONG = (
    "новини", "новостей", "університет", "студент",
    "коледж", "абітурієнт", "розклад", "оголошення", "вступ",
)
# Short generic terms — word-boundary only, so legit "*_info" business handles
# (e.g. @salon_info) are not swept up.
_CHANNEL_NEWS_WORD = re.compile(r"(?<!\w)(інфо|info|news)(?!\w)", re.IGNORECASE)


def _tg_handle(raw: str | None) -> str:
    s = (raw or "").strip().lower().removeprefix("@")
    if "t.me/" in s:
        s = s.split("t.me/", 1)[1]
    return s.strip("/").split("/")[0].split("?")[0]


def is_blocked_telegram(handle: str | None, name: str | None) -> bool:
    if _tg_handle(handle) in _TELEGRAM_HANDLES:
        return True
    text = f"{handle or ''} {name or ''}".lower()
    if any(w in text for w in _CHANNEL_NEWS_STRONG):
        return True
    return bool(_CHANNEL_NEWS_WORD.search(text))
