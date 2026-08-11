# Russian-site geo-gate for gTLD hosts — design

**Status:** APPROVED (design). Track: crawler + backend. Branch: `feat/russian-gtld-geo-gate`.

## Problem

The crawler must never crawl Russian sites (Ukraine, wartime). The current geo-gate
`is_foreign_host` (`crawler/util/hosts.py`) is **TLD-only**: it rejects foreign ccTLDs
(`.ru`/`.by`/`.kz`/…) and foreign IDN-ccTLDs, but allows generic gTLDs (`.com`/`.net`/`.org`)
because legitimate Ukrainian businesses often sit on them. So a Russian site on a gTLD slips
through — live example: `https://spb.boombate.com/...` (Saint-Petersburg subdomain, a Russian
events aggregator) was fetched. Manually blocklisting each such host does not scale.

## Goal

Systematically reject Russian sites on gTLDs, without over-blocking legitimate Ukrainian
sites. Two complementary, low-risk signals: a **Russian-city subdomain** heuristic (catches
`spb.*`/`msk.*` on any TLD) and a **seed blocklist of known Russian apex domains** (catches
apex domains with no city subdomain, and survives DB wipes).

## Design

### Component 1 — Russian-city subdomain heuristic (`crawler/crawler/util/hosts.py`)

- New curated frozenset `_RU_CITY_SUBDOMAINS` of **unambiguous** Russian city/region codes:
  `spb, msk, mow, ekb, nsk, kzn, rostov, sochi, samara, perm, omsk, ufa, krasnodar, volgograd,
  voronezh, tyumen, irkutsk, vladivostok, khabarovsk, chelyabinsk, kaliningrad, saratov,
  barnaul, tomsk, kemerovo`. Deliberately excludes short/ambiguous codes that could collide
  with UA usage.
- Extend `is_foreign_host(value)`: **after** the existing `.ua` allow (a `.ua` host is always
  Ukrainian, whatever its subdomain), reject a host that is a **subdomain** whose leading label
  is a Russian city code:
  ```
  labels = host.split(".")
  if len(labels) >= 3 and labels[0] in _RU_CITY_SUBDOMAINS:
      return True
  ```
  `len >= 3` means the code is a genuine subdomain (`spb.boombate.com` → labels
  `[spb, boombate, com]`), not a second-level domain — so a hypothetical brand SLD named after a
  city is not caught by the heuristic.
- Effect: `spb.boombate.com`, `msk.example.net` → foreign; legit UA/gTLD hosts without a
  Russian-city subdomain (`edclinic.com.ua`, `shop.com`, `mate.academy`) → not foreign; any
  `.ua` host → not foreign (UA-first). Apex Russian domains (`boombate.com`, no city subdomain)
  are **not** the heuristic's job — Component 2 handles those.
- Callers unchanged: `harvest.py` and `osm_feed.py` already gate on `is_foreign_host`, so both
  the active harvest and the OSM feed inherit the rejection.

### Component 2 — seed blocklist of known Russian apex domains (backend Alembic migration)

- New Alembic migration on the current head that upserts known Russian apex domains into
  `blocked_hosts` as `status='approved'` (mirrors the news/social seed migration
  `d4e6f8a0b2c4` from track #34). Seed set: `boombate.com` (the confirmed one; the list is a
  curated constant, extensible). Idempotent upsert (`ON DUPLICATE KEY`/check-then-insert) so it
  is safe on a DB that already has the host (it was added manually this session).
- Reuses the existing blocklist machinery: the crawler no-fetches approved blocked hosts
  (blocklist=no-fetch) and the backend auto-rejects offers from them (#34). Self-grows via the
  admin "block host" flow for apex domains found later.
- Rationale for a migration (not just the manual row): the DB is periodically wiped (Gordon
  wipe); a migration makes the seed durable.

### Data flow

Crawler pass → for each candidate host: `is_foreign_host` (now also rejects Russian-city
subdomains) AND `is_blocked_host` (apex Russian domains from the seed) — either rejects the
fetch before any network call. No new call sites.

## Testing

- **Crawler** (`tests/test_hosts.py` or the existing hosts test): `is_foreign_host` True for
  `spb.boombate.com`, `https://msk.example.net/x`, `www.spb.foo.com` (www stripped, spb kept);
  False for `edclinic.com.ua`, `shop.com`, `mate.academy`, `sub.mate.academy` (non-RU
  subdomain), any `.ua` host with any subdomain, and apex `boombate.com` (heuristic must NOT
  fire on a 2-label host / non-city SLD).
- **Backend**: after `alembic upgrade head`, `blocked_hosts` contains the seed hosts as
  `approved`; migration is idempotent (re-running / pre-existing row does not error);
  `downgrade` removes the seeded rows it added.

## Safety / out of scope

- Over-block guard: the city list is unambiguous Russian codes only; `.ua` is allowed first;
  the heuristic fires only on genuine subdomains (`len >= 3`), never on apex/SLD — so no
  legitimate Ukrainian `.com` business is affected.
- Out of scope (YAGNI): content/whois/language detection (UA sites are bilingual — Russian
  content ≠ Russia); Belarusian city subdomains (add later if needed); ML classification.
