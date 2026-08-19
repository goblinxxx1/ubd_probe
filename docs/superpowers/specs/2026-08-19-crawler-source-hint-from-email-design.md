# Crawler: suggest the real business from an offer page's contact email

**Date:** 2026-08-19
**Status:** Design approved

## Problem

A listing/afisha page re-posts a business's offer. The crawler finds the offer but
attributes it to the listing, not the business, and never crawls the real business.

**Evidence:** `visitlviv.com.ua/uk/promotions/10-for-the-military/` — offer "Ми щиро
вдячні кожному захиснику … −10% на проживання". Attributed to visitlviv (offer #353,
provider "Деталі рекламної акції"). The real business is **Optima Hotels**. Investigated:
- the offer text does **not** name Optima;
- outbound links go to sub-domains (`mice.`, `old.optimahotels.com.ua`), not the promo;
- the business's own apex domain is revealed **only** by a contact email:
  `reservation.hg@optimahotels.com.ua`.

So reliable *attribution* to `optimahotels.com.ua/uk/promotions` is not derivable here.
The realistic fix is to route the crawler to the business by **suggesting its domain as a
new source** (moderator-approved), so it gets crawled directly.

## Goal

When the crawler emits an offer from a page, mine any **contact-email domain that differs
from the page's host** and submit it as a `suggested_source` (website), deduped. The
moderator approves it → the real business is crawled directly (exactly the manual fix
already applied for Optima Hotels, source #50).

Non-goal: changing the afisha offer's attribution (the moderator rejects that card once
the direct-business version appears). Non-goal: mining outbound links (noisy sub-domains);
the email domain is the clean apex signal.

## Design

### New pure helper — `crawler/crawler/discovery/source_hint.py`

```python
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
        blob = it.text or ""
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
```

### Integration — `ActiveHarvester._process_page`

Only fires when the page produced an offer (`collected` non-empty), so business domains
are mined **only** from pages that carry a veteran offer — targeted, not every page.
After the existing `attr.suggest_url_or_handle` loop, before `return structural_provider`:

```python
        if self._source_hint_enabled:
            for hint in business_domains_from_page(items, ctx.host):
                ref = normalize_ref("website", hint)
                if ref not in known:
                    self._api.submit_suggestion({
                        "name": hint, "type": "website",
                        "url_or_handle": f"https://{hint}",
                        "discovered_from_source_id": None,
                        "discovery_note": f"business email domain on {cand.url_or_handle}",
                    })
                    known.add(ref)
                    summary["suggestions"] += 1
```

`ActiveHarvester.__init__` gains `source_hint_enabled=True`; wiring passes
`config.source_hint_enabled`.

### Dedup / noise control

- `known` (the in-pass known-ref set) prevents re-suggesting within a pass.
- The backend's existing suggestion-guard drops a domain that is already an active source
  (204) — so an already-known business is not re-queued.
- Free-mail + page-host + blocked + foreign filters cut the obvious noise. Residual noise
  (e.g. a web-agency's email) lands in the **suggestion** queue (low-stakes, moderator
  reviews) — never in the offer queue.

### Config

`source_hint_enabled: bool = True` — kill-switch, wired `_RawSettings` + `Config` +
`from_settings` (mirror `lang_gate_enabled`).

## Blast radius

- New module `source_hint.py`; one guarded loop in `_process_page`; one `__init__` flag;
  one config bool (3 places) + wiring. No backend/schema change (reuses `submit_suggestion`).

## Risks

1. **Noise in the suggestion queue** (partner/agency emails). Mitigated by the filters and
   the offer-gated trigger; suggestions are reviewed, not auto-crawled. Low.
2. **A business whose contact email is on a free-mail provider** is not hinted. Accepted
   (no clean domain signal); the offer still lands via its normal path.

## Testing

- `source_hint.py`: page with `mailto:reservation.hg@optimahotels.com.ua` on a
  `visitlviv.com.ua` host → `{"optimahotels.com.ua"}`; a free-mail email → excluded;
  an email on the page's own host → excluded; a blocked/foreign email domain → excluded;
  no email → empty set; email only in text (no mailto) → still found.
- `_process_page`: a page that produces an offer AND carries an external business email →
  `submit_suggestion` called once for that domain, deduped against `known`;
  `source_hint_enabled=False` → not called.

## Rollout

Rebuild crawler. Optima Hotels already added manually (source #50); this prevents the next
afisha case from needing manual work.
