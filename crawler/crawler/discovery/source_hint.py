"""Discover a business's OWN domain from an offer page that only re-posts its offer (an
afisha/listing). The clean signal is a contact EMAIL whose domain differs from the page's
host — a re-post page (visitlviv) reveals reservation.hg@optimahotels.com.ua. Suggest that
domain as a source so the real business is crawled directly, instead of attributing the
offer to the listing."""

import re

from crawler.discovery.blocklist import is_blocked_host
from crawler.util.hosts import bare_host, is_foreign_host

_EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)")

# Free / personal mail providers — an email here is NOT a business's own domain.
_FREEMAIL = frozenset({
    "gmail.com", "googlemail.com", "ukr.net", "i.ua", "meta.ua", "bigmir.net",
    "email.ua", "3g.ua", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "icloud.com", "proton.me", "protonmail.com", "gmx.com",
})


def business_domains_from_page(items, page_host) -> set[str]:
    """Bare business domains revealed by contact emails on the page, excluding the page's
    own host, free-mail providers, blocked and foreign hosts. Scans item text AND mailto:
    links across ALL page items (the contact email usually lives in a footer/contact block,
    not the offer block)."""
    ph = bare_host(page_host) if page_host else ""
    out: set[str] = set()
    for it in items:
        blob = getattr(it, "text", None) or ""
        for l in (getattr(it, "links", None) or []):
            if l.lower().startswith("mailto:"):
                blob += " " + l[7:]
        for dom in _EMAIL_RE.findall(blob):
            h = bare_host(dom)
            if not h or h == ph or h in _FREEMAIL:
                continue
            if is_blocked_host(h) or is_foreign_host("https://" + h):
                continue
            out.add(h)
    return out
