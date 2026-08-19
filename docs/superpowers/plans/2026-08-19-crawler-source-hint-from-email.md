# Crawler Source-Hint-From-Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Mine a business's own domain from an offer page's contact email (when it differs from the page host) and suggest it as a new source, so re-posted afisha offers route the crawler to the real business.

**Architecture:** New pure helper `source_hint.business_domains_from_page`; a guarded loop in `ActiveHarvester._process_page` (fires only when the page produced an offer) submits each domain via the existing `submit_suggestion`.

**Tech Stack:** Python 3, pytest; Docker Compose.

## Global Constraints

- Ukrainian-only: no Russian text in code/tests; foreign/blocked email domains excluded.
- Reuse `bare_host`, `is_foreign_host` (`crawler/util/hosts.py`), `is_blocked_host` (`discovery/blocklist.py`), `normalize_ref` (`discovery/passive.py`) — all importable.
- Trigger ONLY on offer-bearing pages (inside `_process_page`'s `collected` block). Dedup via `known`.
- Config mirrors `lang_gate_enabled` (config.py lines 106 / 223 / 362).
- Crawler tests: from `crawler/`, `./.venv/Scripts/python.exe -m pytest ...`.

---

## Task 1: `source_hint.py` + tests

**Files:** Create `crawler/crawler/discovery/source_hint.py`; Test `crawler/tests/test_source_hint.py`.

- [ ] **Step 1: failing test** — `crawler/tests/test_source_hint.py`

```python
from types import SimpleNamespace

from crawler.discovery.source_hint import business_domains_from_page


def _it(text="", links=None):
    return SimpleNamespace(text=text, links=links or [])


def test_email_domain_differing_from_host_is_hinted():
    items = [_it("Бронювання: reservation.hg@optimahotels.com.ua")]
    assert business_domains_from_page(items, "visitlviv.com.ua") == {"optimahotels.com.ua"}


def test_mailto_link_is_read():
    items = [_it(links=["mailto:info@shop.com.ua", "https://x/y"])]
    assert business_domains_from_page(items, "afisha.ua") == {"shop.com.ua"}


def test_freemail_and_same_host_and_foreign_excluded():
    items = [_it("a@gmail.com b@visitlviv.com.ua c@shop.ru d@biz.ua")]
    assert business_domains_from_page(items, "visitlviv.com.ua") == {"biz.ua"}


def test_no_email_is_empty():
    assert business_domains_from_page([_it("нема пошти тут")], "x.ua") == set()
```

- [ ] **Step 2: run → fail** — `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_source_hint.py -q` → ModuleNotFoundError.

- [ ] **Step 3: implement** — `crawler/crawler/discovery/source_hint.py`

```python
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
```

- [ ] **Step 4: run → pass.**  **Step 5: commit** `git add crawler/crawler/discovery/source_hint.py crawler/tests/test_source_hint.py && git commit -m "feat(crawler): source_hint — business domain from offer-page contact email"`

---

## Task 2: harvest integration + config + wiring

**Files:** Modify `crawler/crawler/discovery/harvest.py`, `crawler/crawler/config.py`, `crawler/crawler/wiring.py`; Test `crawler/tests/test_active_harvest.py`, `crawler/tests/test_config.py`.

- [ ] **Step 1: failing test** — append to `crawler/tests/test_active_harvest.py`

```python
def test_source_hint_suggests_external_business_email_domain(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx, **kw: type("A", (), {
                            "provider": "Afisha", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Afisha"})())
    api = FakeApi()
    item = RawItem(source_id=None, platform="website", key="k",
                   text="Знижка 20% для військових. Пошта: reservation@optimahotels.com.ua",
                   url="https://visitlviv.com.ua/promo", links=[], site_name="Afisha")
    harv = ActiveHarvester(api, {"website": FakeFetcher([item])}, GateExtractor(),
                           rate_limiter=None, fetch_budget=5)
    harv.harvest([_cand(url="https://visitlviv.com.ua/promo")], cats=None, known=set(),
                 summary=_summary())
    hinted = [s["url_or_handle"] for s in api.suggested]
    assert "https://optimahotels.com.ua" in hinted


def test_source_hint_disabled(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx, **kw: type("A", (), {
                            "provider": "Afisha", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Afisha"})())
    api = FakeApi()
    item = RawItem(source_id=None, platform="website", key="k",
                   text="Знижка 20% для військових. reservation@optimahotels.com.ua",
                   url="https://visitlviv.com.ua/promo", links=[], site_name="Afisha")
    harv = ActiveHarvester(api, {"website": FakeFetcher([item])}, GateExtractor(),
                           rate_limiter=None, fetch_budget=5, source_hint_enabled=False)
    harv.harvest([_cand(url="https://visitlviv.com.ua/promo")], cats=None, known=set(),
                 summary=_summary())
    assert all("optimahotels" not in s["url_or_handle"] for s in api.suggested)
```

> `GateExtractor` emits an offer for text containing "%" (here "20%"), so the page is offer-bearing and `_process_page` reaches the hint loop. `attribute` is stubbed to return an offer with `suggest_url_or_handle=None` so only the hint path adds a suggestion.

- [ ] **Step 2: run → fail** — `source_hint_enabled` unknown / no hinted suggestion.

- [ ] **Step 3: implement harvest** — `crawler/crawler/discovery/harvest.py`

Import near the top:
```python
from crawler.discovery.source_hint import business_domains_from_page
```
`ActiveHarvester.__init__` tail param + store:
```python
                 lang_block_store=None, editorial_gate_enabled=True,
                 source_hint_enabled=True):
```
```python
        self._editorial_gate_enabled = editorial_gate_enabled
        self._source_hint_enabled = source_hint_enabled
```
In `_process_page`, immediately before `return structural_provider` (after the existing `attr.suggest_url_or_handle` loop):
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

- [ ] **Step 4: config** — add `source_hint_enabled: bool = True` beside `lang_gate_enabled` in `_RawSettings` and `Config`; add `source_hint_enabled=s.source_hint_enabled,` beside the mapping. Append to `crawler/tests/test_config.py`:

```python
def test_source_hint_defaults_on(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOURCE_HINT_ENABLED", raising=False)
    assert load_config().source_hint_enabled is True
```

- [ ] **Step 5: wiring** — in `crawler/crawler/wiring.py` `ActiveHarvester(...)`:
```python
                                    editorial_gate_enabled=config.editorial_gate_enabled,
                                    source_hint_enabled=config.source_hint_enabled)
```

- [ ] **Step 6: run** — `./.venv/Scripts/python.exe -c "import crawler.wiring"` + `pytest tests/test_active_harvest.py tests/test_config.py -q` + full suite `pytest -q`. Expected PASS.

- [ ] **Step 7: commit** `git add crawler/crawler/discovery/harvest.py crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_active_harvest.py crawler/tests/test_config.py && git commit -m "feat(crawler): suggest business source from offer-page contact email"`

---

## Task 3: Rollout

- [ ] Rebuild crawler: `docker compose build crawler && docker compose up -d crawler`.
- [ ] Verify (live): fetch visitlviv promo via the fetcher and confirm `business_domains_from_page(items, "visitlviv.com.ua")` returns `{"optimahotels.com.ua"}`.

---

## Self-Review

**Spec coverage:** helper (email→domain, filters) → Task 1; offer-gated suggestion + config + wiring → Task 2; rollout+verify → Task 3. ✓
**Placeholder scan:** none. **Type consistency:** `business_domains_from_page(items, page_host) -> set[str]`; `ActiveHarvester(..., source_hint_enabled=True)`; `config.source_hint_enabled` produced/consumed consistently.
