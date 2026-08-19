# Crawler Junk-Host Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate `.media` media-outlet hosts at the first crawl and block/clean the three confirmed junk hosts, without over-blocking legitimate businesses.

**Architecture:** One structural addition — treat the `.media` TLD as a media host inside the existing `is_news_host` pre-fetch gate (`host_quality.py`), which already drops candidates before any fetch. Then an operational rollout: seed three confirmed junk hosts into the backend `blocked_hosts` table and reject their existing queue offers.

**Tech Stack:** Python 3, pytest; MySQL (`ubd`) via `docker exec`; Docker Compose.

## Global Constraints

- Ukrainian-only project: no Russian text in code/tests/seeds.
- Structural, not a host list, for the code gate: `.media` TLD only. **Do NOT** add entertainment tokens (`kino`, `film`, …) — they block legitimate cinemas (`planetakino.ua` is a published offer, #173).
- Do **not** change `media_autoblock` or `media_autoblock_crawls` (it works; registry confirms crawl-2 blocking).
- Do **not** block `gospital.itmed.org` (a hospital; its false positive is Track 4).
- `is_news_host` lives in `crawler/crawler/discovery/host_quality.py`; it is already wired into the harvest pre-fetch gate — no new call site.
- Run tests from `crawler/` via the venv: `./.venv/Scripts/python.exe -m pytest ...`.
- DB password: `MYSQL_ROOT_PASSWORD` in `D:\ubd_probe\.env`; DB name `ubd`; container `ubd_probe-db-1`.

---

## File Structure

- Modify `crawler/crawler/discovery/host_quality.py` — add `_MEDIA_TLDS = {"media"}` and a TLD check at the top of `is_news_host`.
- Modify `crawler/tests/test_host_quality.py` — add `.media` positive cases + a `planetakino.ua` negative guard.
- Rollout only (no repo change): DB seed + queue reject + container rebuild.

---

## Task 1: `.media` TLD in `is_news_host`

**Files:**
- Modify: `crawler/crawler/discovery/host_quality.py:47-55`
- Test: `crawler/tests/test_host_quality.py`

**Interfaces:**
- Produces: `is_news_host(value)` additionally returns True when the host's TLD label is `media` (e.g. `moreliudei.media`), unchanged otherwise.

- [ ] **Step 1: Write the failing tests** — append to `crawler/tests/test_host_quality.py`

```python
def test_media_tld_is_news_host():
    assert is_news_host("moreliudei.media") is True
    assert is_news_host("https://suspilne.media/news/123") is True   # public broadcaster
    assert is_news_host("x.media") is True
    # existing token behavior still holds
    assert is_news_host("https://www.groza-news.info/x") is True
    assert is_news_host("kyiv.news") is True


def test_media_gate_does_not_block_cinemas_or_business():
    # cinemas are legitimate veteran-discount businesses (planetakino.ua is published)
    assert is_news_host("planetakino.ua") is False
    assert is_news_host("https://planetakino.ua/discounts") is False
    assert is_news_host("uaserials.com") is False       # .com — caught by seed, not this gate
    assert is_news_host("shop.ua") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_host_quality.py -q`
Expected: FAIL — `test_media_tld_is_news_host` asserts `moreliudei.media` True, but current `is_news_host` has no `.media` handling.

- [ ] **Step 3: Add the media-TLD set and check** — edit `crawler/crawler/discovery/host_quality.py`

Replace the `_NEWS_TOKENS` block's `is_news_host` (lines ~47-55) so it reads:

```python
_NEWS_TOKENS = ("news", "novyny", "gazeta", "visti", "pravda")

# TLDs that denote a media outlet regardless of the label (news portals, magazines).
# .media hosts are essentially always media; verified 0 published offers on .media.
_MEDIA_TLDS = {"media"}


def is_news_host(value: str | None) -> bool:
    """True, якщо хост — новинний/медійний ресурс (не джерело офера УБД): новинний
    токен у мітці АБО медійний TLD (.media)."""
    host = bare_host(value)
    if not host:
        return False
    labels = host.split(".")
    if labels[-1] in _MEDIA_TLDS:
        return True
    return any(tok in label for label in labels for tok in _NEWS_TOKENS)
```

(Keep the existing `_NEWS_TOKENS` comment lines above it unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_host_quality.py -q`
Expected: PASS (existing + 2 new tests).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS across the crawler suite.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/host_quality.py crawler/tests/test_host_quality.py
git commit -m "feat(crawler): treat .media TLD as media host in is_news_host"
```

---

## Task 2: Rollout — seed offenders, reject queue, deploy

**Files:** none in-repo (operates on the `blocked_hosts` table, the queue, and the container image).

This task has no test cycle of its own — it deploys Task 1 and performs one-off data cleanup. Run it only after Task 1 is committed and reviewed.

- [ ] **Step 1: Rebuild + restart the crawler (ships the `.media` gate)**

```bash
docker compose build crawler && docker compose up -d crawler
```

- [ ] **Step 2: Seed the three confirmed junk hosts into `blocked_hosts`**

```bash
PW=$(grep -h '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec ubd_probe-db-1 mysql -uroot -p"$PW" ubd -e "
INSERT IGNORE INTO blocked_hosts (host, status, media_ratio, aggregator_ratio, support, created_at)
VALUES ('uaserials.com','approved',0,0,0,NOW()),
       ('akzent.zp.ua','approved',0,0,0,NOW()),
       ('moreliudei.media','approved',0,0,0,NOW());"
```

Expected: 3 rows inserted (or fewer if a host is already present — `INSERT IGNORE`).

- [ ] **Step 3: Reject the existing junk offers in the queue**

```bash
PW=$(grep -h '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec ubd_probe-db-1 mysql -uroot -p"$PW" ubd -e "
UPDATE offers SET status='rejected'
WHERE status='pending_review'
  AND (article_url LIKE '%uaserials.com%' OR site_url LIKE '%uaserials.com%'
    OR article_url LIKE '%akzent.zp.ua%'  OR site_url LIKE '%akzent.zp.ua%'
    OR article_url LIKE '%moreliudei.media%' OR site_url LIKE '%moreliudei.media%');
SELECT ROW_COUNT() AS rejected;"
```

Expected: `rejected` = 6 (uaserials ×4 = #338-341, akzent #336, moreliudei #337). If the count differs, list the matching rows first with a SELECT and confirm they are the intended junk offers before proceeding.

- [ ] **Step 4: Restart crawler so it reloads the blocklist from the backend**

The crawler loads `blocked_hosts` at startup (`build_runner` → `blocklist.reload_learned(api.list_blocked_hosts())`). Restart to pick up the seeded rows:

```bash
docker compose restart crawler
```

- [ ] **Step 5: Verify the gate + block are live**

```bash
docker compose exec -T crawler python -c "
from crawler.discovery.host_quality import is_news_host
from crawler.discovery.blocklist import is_blocked_host
print('media gate  moreliudei.media:', is_news_host('moreliudei.media'))
print('cinema safe planetakino.ua :', is_news_host('planetakino.ua'))
print('blocked uaserials.com      :', is_blocked_host('uaserials.com'))
print('blocked akzent.zp.ua       :', is_blocked_host('https://akzent.zp.ua/x'))
"
```

Expected: `True`, `False`, `True`, `True`.

- [ ] **Step 6: Confirm queue is clean**

```bash
PW=$(grep -h '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec ubd_probe-db-1 mysql -uroot -p"$PW" ubd -e "
SELECT COUNT(*) AS junk_still_pending FROM offers
WHERE status='pending_review'
  AND (article_url LIKE '%uaserials.com%' OR article_url LIKE '%akzent.zp.ua%'
    OR article_url LIKE '%moreliudei.media%');"
```

Expected: `junk_still_pending` = 0.

---

## Self-Review

**Spec coverage:**
- `.media` TLD gate in `is_news_host` → Task 1. ✓
- Seed uaserials / akzent / moreliudei into `blocked_hosts` → Task 2 Step 2. ✓
- Reject existing junk queue offers → Task 2 Step 3. ✓
- No `media_autoblock` change, no `gospital` block, no entertainment tokens → enforced by Global Constraints + the cinema guard test. ✓
- Over-block check (0 published on `.media`; cinema not gated) → Task 1 test `test_media_gate_does_not_block_cinemas_or_business`. ✓
- Rollout (rebuild, seed, reject, verify) → Task 2. ✓

**Placeholder scan:** none — all commands and code are concrete.

**Type consistency:** `is_news_host(value: str | None) -> bool` unchanged in signature; only its body gains the `_MEDIA_TLDS` check. `is_blocked_host` used in verification is the existing predicate. Test host strings are consistent across tasks (`moreliudei.media`, `planetakino.ua`, `uaserials.com`).
