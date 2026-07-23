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
}
_STOCK = {"depositphotos.com", "shutterstock.com", "istockphoto.com", "freepik.com"}
_SOCIAL = {
    "tiktok.com", "youtube.com", "youtu.be", "pinterest.com",
    "twitter.com", "x.com",
}
_BLOCKED = _MEDIA | _STOCK | _SOCIAL

_LEARNED: frozenset[str] = frozenset()


def reload_learned(hosts) -> None:
    """Replace the learned media/aggregator host set (approved via the Vue audit).
    None/empty ⇒ SEED-only, byte-equivalent to prior behaviour."""
    global _LEARNED
    if not hosts:
        _LEARNED = frozenset()
        return
    norm = {bare_host(h) for h in hosts if h and h.strip()}
    _LEARNED = frozenset(n for n in norm if n)


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
