"""Hosts that must never be attributed as offer providers or offer sources:
news media, government, stock-photo banks, social-video aggregators."""

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


def is_blocked_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.strip().lower().removeprefix("www.")
    if not host:
        return False
    if host == "gov.ua" or host.endswith(".gov.ua"):
        return True
    return any(host == d or host.endswith("." + d) for d in _BLOCKED)
