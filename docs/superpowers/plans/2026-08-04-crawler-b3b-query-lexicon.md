# B3b — Self-growing query lexicon — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mine service/category terms from approved offers into a human-audited LEARNED query lexicon that feeds `build_grid` as `{service} {audience}` phrases, growing the search space weekly.

**Architecture:** Mirror the existing promo/marketing autofill (`crawler/crawler/learn/`) for a QUERY lexicon. Two sources: structural `offer_categories` (direct to LEARNED, moderator-vetted) and text nouns (pymorphy3 NOUN + log-odds → audit-gate). `build_grid` gains a `services` axis (`{service} × GEO_AUDIENCES`, capped). Soft reject (non-permanent, categories > stoplist). One minimal read-only backend field (`ApprovedOfferOut.categories`). Empty LEARNED = byte-eq the B3a 1701 grid.

**Tech Stack:** Python 3, pytest, pymorphy3 (already a dep, `lang="uk"`). Backend: FastAPI/SQLAlchemy/Pydantic.

## Global Constraints

- Empty LEARNED (no learned services) ⇒ `build_grid()` identical to B3a (1701). `query_lexicon_enabled=False` ⇒ wiring passes `services=[]` ⇒ 1701.
- Byte-stable prefix: base 351 + geo 1350 (first 1701 entries) unchanged; services block is appended AFTER.
- Service phrases use the audience-targeted template ONLY: `{service} {audience}` over `GEO_AUDIENCES` (6). No `{intent}{service}`, no city multiplier on services.
- Cap: at most `query_lexicon_max_terms` (default 40) services enter the grid — categories first, then text-mined by z desc.
- Nominative case (matches build_grid). `provider` is NOT mined (brands are not a query axis).
- Injection-hardening: source is moderator-approved offers only; text terms pass a human audit-gate before entering the live grid.
- Promo autofill path must remain byte-equivalent: `mine()` default tokenizer unchanged; existing `audit.reject` (flat stoplist) untouched; existing config fields untouched.
- Crawler tests run from `crawler/`: `python -m pytest -q`. Backend tests from `backend/`: `./.venv/Scripts/python.exe -m pytest -q` (needs mysql-container :3306). Full suites green at end of every task.
- Spec: `docs/superpowers/specs/2026-08-04-crawler-b3b-query-lexicon-design.md`.

## Interfaces (shared across tasks — use these exact names/signatures)

- `crawler.learn.tokenize.service_terms(text: str) -> list[str]` — noun lemmas + noun-noun bigrams.
- `crawler.learn.miner.mine(rows, known_stems=(), stoplist=(), snowball_weight=3, alpha=0.5, pos_weight=2.0, tokenizer=tokenize)` — new trailing `tokenizer` kwarg.
- `crawler.discovery.query_lexicon.reload_learned(path: str | None) -> None`; `learned_services() -> tuple[str, ...]` (categories first, then z desc, deduped).
- `crawler.discovery.query_grid.build_grid(cities=None, services=None) -> list[str]` — services `None`→`()`.
- `crawler.learn.query_stoplist.load_blocked(path) -> dict[str, float]`; `reject(term, candidates_path, stoplist_path) -> None`; `unstop(term, stoplist_path) -> None`; `is_suppressed(term, z, blocked, factor) -> bool`.
- `crawler.learn.run_query_miner.run_query_miner(config) -> int`.
- `crawler.learn.bootstrap_query_lexicon.bootstrap(config, api, recorder) -> tuple[int, int]` (categories seeded, candidates written).
- config fields (both raw `_RawSettings` and `Config`): `query_lexicon_enabled: bool = True`, `query_lexicon_learned_path="/data/query_lexicon_learned.json"`, `query_candidates_path="/data/query_candidates.json"`, `query_stoplist_path="/data/query_stoplist.json"`, `query_lexicon_max_terms=40`, `query_lexicon_resurface_factor=2.0`, `query_miner_min_domain_support=3`, `query_miner_min_logodds=1.5`, `query_miner_max_candidates_per_run=50`.

---

### Task 1: Backend — `ApprovedOfferOut.categories`

**Files:**
- Modify: `backend/app/routers/internal.py` (`ApprovedOfferOut` schema ~line 102; endpoint ~line 112)
- Test: `backend/tests/test_internal.py`

**Interfaces:**
- Produces: `/api/internal/approved-offers` rows now include `categories: list[str]` (offer_category names). Additive; existing `text`/`host`/`approved_at` unchanged.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_internal.py` (mirror an existing approved-offers test's setup — create a published offer WITH an offer_category, then GET). Use the file's existing client/fixtures:

```python
def test_approved_offers_include_category_names(client, db_session):
    # create a published offer with an offer_category, then fetch
    off = _make_published_offer(db_session, title="Стоматологія Люкс",
                                 category_names=["Медицина"])
    r = client.get("/api/internal/approved-offers",
                   headers={"X-API-Key": _KEY})
    assert r.status_code == 200
    row = next(o for o in r.json() if "Стоматологія Люкс" in o["text"])
    assert row["categories"] == ["Медицина"]
```

If the file has no `_make_published_offer`/`category_names` helper, construct the offer inline the same way the nearest existing published-offer test does (via `offer_crud.create_offer` with `offer_category_ids`), and read the API-key constant already used in the file. The assertion that matters: the response row carries `categories == ["Медицина"]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_internal.py -k category -q`
Expected: FAIL — `KeyError: 'categories'` (field absent).

- [ ] **Step 3: Add the field + mapping**

In `backend/app/routers/internal.py`, add to `ApprovedOfferOut`:

```python
class ApprovedOfferOut(BaseModel):
    text: str
    host: str
    approved_at: datetime | None = None
    categories: list[str] = []
```

(Keep the existing fields exactly as they are; only add `categories`.) In `list_approved_offers`, add the mapping:

```python
        ApprovedOfferOut(
            text=f"{o.title}\n{o.description or ''}".strip(),
            host=_host(o.site_url or o.article_url),
            approved_at=o.updated_at,
            categories=[c.name for c in o.offer_categories],
        )
```

(`o.offer_categories` is already `selectin`-loaded on the model — no query change needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_internal.py -q`
Expected: PASS (all internal tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/internal.py backend/tests/test_internal.py
git commit -m "feat(backend): ApprovedOfferOut.categories for query-lexicon miner (B3b)"
```

---

### Task 2: Noun tokenizer + `mine` tokenizer param

**Files:**
- Modify: `crawler/crawler/learn/tokenize.py` (add `service_terms`)
- Modify: `crawler/crawler/learn/miner.py` (add `tokenizer` kwarg)
- Test: `crawler/tests/test_tokenize.py` (create if absent), `crawler/tests/test_miner.py`

**Interfaces:**
- Produces: `service_terms(text) -> list[str]` (noun lemmas + noun-noun bigrams); `mine(..., tokenizer=tokenize)`.

- [ ] **Step 1: Write the failing tests**

Create/extend `crawler/tests/test_tokenize.py`:

```python
from crawler.learn.tokenize import service_terms


def test_service_terms_keeps_nouns_drops_verbs_and_adjectives():
    out = service_terms("купуйте дешеву каву")   # verb, adjective, noun
    assert "кава" in out
    assert "купуйте" not in out and "дешевий" not in out


def test_service_terms_noun_bigrams():
    out = service_terms("автомийка самообслуговування")
    assert "автомийка" in out and "самообслуговування" in out
    assert "автомийка самообслуговування" in out   # noun-noun bigram


def test_service_terms_empty_is_empty():
    assert service_terms("") == []
```

Add to `crawler/tests/test_miner.py`:

```python
from crawler.learn.miner import mine


def test_mine_default_tokenizer_is_unchanged():
    rows = [{"text": "знижка знижка", "label": "pass", "host": "a.com", "snowball": True},
            {"text": "новини", "label": "fail", "host": "b.com"}]
    # default tokenizer path still produces scores (byte-eq promo behavior)
    scores = mine(rows)
    assert any(s.term == "знижка" for s in scores)


def test_mine_accepts_custom_tokenizer():
    rows = [{"text": "стоматологія акція", "label": "pass", "host": "a.com"}]
    scores = mine(rows, tokenizer=lambda t: ["стоматологія"] if t else [])
    assert [s.term for s in scores] == ["стоматологія"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_tokenize.py tests/test_miner.py -q`
Expected: FAIL — `ImportError: cannot import name 'service_terms'`; `mine() got unexpected keyword argument 'tokenizer'`.

- [ ] **Step 3: Implement `service_terms`**

Append to `crawler/crawler/learn/tokenize.py`:

```python
def service_terms(text: str) -> list[str]:
    """Noun-only lemmas (+ noun-noun bigrams) for the QUERY miner: service/category
    terms, dropping verbs/adjectives/adverbs. Deterministic via the pinned uk dict."""
    nouns: list[str] = []
    for w in _WORD.findall(text or ""):
        parsed = _morph.parse(w.lower())
        if parsed and parsed[0].tag.POS == "NOUN":
            nouns.append(parsed[0].normal_form)
    bigrams = [f"{a} {b}" for a, b in zip(nouns, nouns[1:])]
    return nouns + bigrams
```

- [ ] **Step 4: Add `tokenizer` param to `mine`**

In `crawler/crawler/learn/miner.py`, change the signature and the tokenize call only:

```python
def mine(rows, known_stems=(), stoplist=(), snowball_weight: int = 3, alpha: float = 0.5,
         pos_weight: float = 2.0, tokenizer=tokenize):
```

and inside the loop replace `toks = set(tokenize(r.get("text", "")))` with:

```python
        toks = set(tokenizer(r.get("text", "")))
```

(Everything else unchanged; default `tokenizer=tokenize` keeps promo byte-eq.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_tokenize.py tests/test_miner.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/learn/tokenize.py crawler/crawler/learn/miner.py crawler/tests/test_tokenize.py crawler/tests/test_miner.py
git commit -m "feat(crawler): service_terms noun tokenizer + mine(tokenizer=) param (B3b)"
```

---

### Task 3: `query_lexicon` consumer

**Files:**
- Create: `crawler/crawler/discovery/query_lexicon.py`
- Test: `crawler/tests/test_query_lexicon.py`

**Interfaces:**
- Produces: `reload_learned(path)`, `learned_services() -> tuple[str, ...]` (categories first — entries with `source=="category"` in file order — then remaining by `z` desc; deduped case-insensitively).

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_query_lexicon.py`:

```python
import json

from crawler.discovery import query_lexicon as ql


def _write(tmp_path, entries):
    p = tmp_path / "q_learned.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return str(p)


def test_learned_services_categories_first_then_by_z(tmp_path):
    path = _write(tmp_path, [
        {"term": "автосервіс", "z": 4.0},
        {"term": "медицина", "source": "category"},
        {"term": "стоматологія", "z": 9.0},
    ])
    ql.reload_learned(path)
    assert ql.learned_services() == ("медицина", "стоматологія", "автосервіс")


def test_reload_none_or_missing_is_empty(tmp_path):
    ql.reload_learned(None)
    assert ql.learned_services() == ()
    ql.reload_learned(str(tmp_path / "nope.json"))
    assert ql.learned_services() == ()


def test_dedup_casefold(tmp_path):
    path = _write(tmp_path, [{"term": "Кава", "z": 2.0}, {"term": "кава", "z": 1.0}])
    ql.reload_learned(path)
    assert ql.learned_services() == ("Кава",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_query_lexicon.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `crawler/crawler/discovery/query_lexicon.py`:

```python
"""LEARNED query lexicon (mirror of promo_lexicon): service/category terms that
feed build_grid as "{service} {audience}". Grown by the query miner + human audit;
structural categories seeded directly. Empty = byte-eq the static grid."""

import json

_learned: tuple[str, ...] = ()


def reload_learned(path: str | None) -> None:
    global _learned
    if not path:
        _learned = ()
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        _learned = ()
        return
    entries = [e for e in data if isinstance(e, dict) and e.get("term")]
    cats = [e for e in entries if e.get("source") == "category"]
    rest = sorted((e for e in entries if e.get("source") != "category"),
                  key=lambda e: (-(e.get("z") or 0.0), e["term"]))
    seen: set[str] = set()
    out: list[str] = []
    for e in (*cats, *rest):
        key = e["term"].casefold()
        if key not in seen:
            seen.add(key)
            out.append(e["term"])
    _learned = tuple(out)


def learned_services() -> tuple[str, ...]:
    return _learned
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_query_lexicon.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/query_lexicon.py crawler/tests/test_query_lexicon.py
git commit -m "feat(crawler): query_lexicon LEARNED consumer (categories-first, z-sorted) (B3b)"
```

---

### Task 4: `build_grid` services block

**Files:**
- Modify: `crawler/crawler/discovery/query_grid.py` (`build_grid`)
- Test: `crawler/tests/test_query_grid.py`

**Interfaces:**
- Consumes: `GEO_AUDIENCES` (6) from Task-nothing (already in file).
- Produces: `build_grid(cities=None, services=None)` — services `None`→`()`; appends `{service} {aud}` over `GEO_AUDIENCES` after the geo block.

- [ ] **Step 1: Write the failing tests**

Add to `crawler/tests/test_query_grid.py`:

```python
def test_services_block_appended_after_geo():
    base = build_grid()                       # 1701, no services
    g = build_grid(services=["стоматологія", "автосервіс"])
    assert g[:len(base)] == base              # byte-stable: services appended after
    added = len(g) - len(base)
    assert added == 2 * len(GEO_AUDIENCES)    # 6 per service
    assert "стоматологія ветерани" in g
    assert "автосервіс військові" in g


def test_services_none_or_empty_is_byte_eq():
    assert build_grid(services=None) == build_grid()
    assert build_grid(services=[]) == build_grid()
```

(Ensure `GEO_AUDIENCES` is in the import line at the top of the test file — it was added in B3a.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_query_grid.py -q`
Expected: FAIL — `build_grid() got unexpected keyword argument 'services'`.

- [ ] **Step 3: Implement**

In `crawler/crawler/discovery/query_grid.py`, change `build_grid` to accept `services` and append the block after the geo loop:

```python
def build_grid(cities: list[str] | None = None,
               services: list[str] | None = None) -> list[str]:
    """351 base + geo block (B3a) + service block (B3b: "{service} {audience}" over
    GEO_AUDIENCES). Base+geo order unchanged (byte-stable 1701 prefix); services
    appended after. `cities=[]`→no geo; `services` None/[]→no service block (byte-eq)."""
    city_list = list(GRID_CITIES) if cities is None else list(cities)
    svc_list = list(services or ())
    seen: set[str] = set()
    out: list[str] = []

    def _add(q: str) -> None:
        key = q.casefold()
        if q and key not in seen:
            seen.add(key)
            out.append(q)

    for head in INTENT_FORMS:                # base 351 — order unchanged
        for aud in AUDIENCE_FORMS:
            _add(f"{head} {aud}".strip())
    for head in GEO_INTENTS:                 # geo block: intent → audience → city
        for aud in GEO_AUDIENCES:
            for city in city_list:
                _add(f"{head} {aud} {city}".strip())
    for svc in svc_list:                     # service block (B3b): service → audience
        for aud in GEO_AUDIENCES:
            _add(f"{svc} {aud}".strip())
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_query_grid.py -q`
Expected: PASS (existing 1701/byte-stable tests still green; new service tests pass).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/query_grid.py crawler/tests/test_query_grid.py
git commit -m "feat(crawler): build_grid services block {service}{audience} (B3b)"
```

---

### Task 5: Soft query stoplist (`query_stoplist.py`)

**Files:**
- Create: `crawler/crawler/learn/query_stoplist.py`
- Test: `crawler/tests/test_query_stoplist.py`

**Interfaces:**
- Produces: `load_blocked(path) -> dict[str, float]`; `reject(term, candidates_path, stoplist_path)`; `unstop(term, stoplist_path)`; `is_suppressed(term, z, blocked, factor) -> bool`.
- Stoplist file format: JSON list of `{"term": str, "z": float}`.

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_query_stoplist.py`:

```python
import json

from crawler.learn import query_stoplist as qs


def _cands(tmp_path):
    p = tmp_path / "q_cand.json"
    p.write_text(json.dumps([{"term": "кава", "z": 3.0, "support": 4}]), encoding="utf-8")
    return str(p)


def test_reject_writes_term_and_z_and_drops_candidate(tmp_path):
    cand = _cands(tmp_path)
    stop = str(tmp_path / "q_stop.json")
    qs.reject("кава", cand, stop)
    assert qs.load_blocked(stop) == {"кава": 3.0}
    assert json.loads(open(cand, encoding="utf-8").read()) == []   # removed from queue


def test_is_suppressed_until_z_exceeds_factor():
    blocked = {"кава": 3.0}
    assert qs.is_suppressed("кава", 5.0, blocked, factor=2.0) is True    # 5 <= 3*2
    assert qs.is_suppressed("кава", 6.5, blocked, factor=2.0) is False   # 6.5 > 6 -> resurface
    assert qs.is_suppressed("чай", 1.0, blocked, factor=2.0) is False    # not blocked


def test_unstop_removes_term(tmp_path):
    stop = str(tmp_path / "q_stop.json")
    qs.reject("кава", _cands(tmp_path), stop)
    qs.unstop("кава", stop)
    assert qs.load_blocked(stop) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_query_stoplist.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `crawler/crawler/learn/query_stoplist.py`:

```python
"""Soft, non-permanent query stoplist: records {term, z_at_reject}. A rejected term
stays suppressed only while its new z ≤ z_at_reject × resurface_factor — so a service
that gains much stronger support later can resurface. Categories override (unstop)."""

import json
import os


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_blocked(path) -> dict[str, float]:
    return {e["term"]: float(e.get("z") or 0.0)
            for e in _load(path, []) if isinstance(e, dict) and e.get("term")}


def reject(term, candidates_path, stoplist_path) -> None:
    cand = next((c for c in _load(candidates_path, []) if c.get("term") == term), {})
    stop = _load(stoplist_path, [])
    if not any(e.get("term") == term for e in stop):
        stop.append({"term": term, "z": float(cand.get("z") or 0.0)})
        _save(stoplist_path, stop)
    _save(candidates_path, [c for c in _load(candidates_path, []) if c.get("term") != term])


def unstop(term, stoplist_path) -> None:
    stop = _load(stoplist_path, [])
    kept = [e for e in stop if e.get("term") != term]
    if len(kept) != len(stop):
        _save(stoplist_path, kept)


def is_suppressed(term, z, blocked, factor) -> bool:
    if term not in blocked:
        return False
    return z <= blocked[term] * factor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_query_stoplist.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/query_stoplist.py crawler/tests/test_query_stoplist.py
git commit -m "feat(crawler): soft non-permanent query stoplist + resurface (B3b)"
```

---

### Task 6: `run_query_miner` orchestrator

**Files:**
- Create: `crawler/crawler/learn/run_query_miner.py`
- Test: `crawler/tests/test_run_query_miner.py`

**Interfaces:**
- Consumes: `read_corpus`, `mine` (Task 2), `survivors`, `query_lexicon` (Task 3), `query_stoplist` (Task 5), `write_candidates` (from `learn.audit`).
- Produces: `run_query_miner(config) -> int` (candidates written). Uses `service_terms` tokenizer, `known_stems=query_lexicon.learned_services()`, soft-stoplist post-filter, query-specific config paths/thresholds.

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_run_query_miner.py`:

```python
import json
import types

from crawler.learn.run_query_miner import run_query_miner


def _cfg(tmp_path, **over):
    corpus = tmp_path / "corpus.jsonl"
    # two approved (pass) offers mentioning a service noun on distinct hosts; one fail
    rows = [
        {"text": "стоматологія знижка", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "стоматологія акція", "label": "pass", "host": "b.com", "snowball": True},
        {"text": "стоматологія клініка", "label": "pass", "host": "c.com", "snowball": True},
        {"text": "новини політика", "label": "fail", "host": "n.com"},
    ]
    corpus.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    d = dict(corpus_path=str(corpus),
             query_candidates_path=str(tmp_path / "q_cand.json"),
             query_stoplist_path=str(tmp_path / "q_stop.json"),
             query_lexicon_learned_path=str(tmp_path / "q_learned.json"),
             query_miner_min_domain_support=2, query_miner_min_logodds=0.1,
             query_miner_max_candidates_per_run=50, query_lexicon_resurface_factor=2.0)
    d.update(over)
    return types.SimpleNamespace(**d)


def test_run_query_miner_writes_service_candidates(tmp_path):
    cfg = _cfg(tmp_path)
    n = run_query_miner(cfg)
    cand = json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())
    terms = [c["term"] for c in cand]
    assert "стоматологія" in terms
    assert "політика" not in terms          # noun but from FAIL side -> low/neg z
    assert n == len(cand)


def test_run_query_miner_respects_soft_stoplist(tmp_path):
    cfg = _cfg(tmp_path)
    # pre-block "стоматологія" with a high z so factor keeps it suppressed
    open(cfg.query_stoplist_path, "w", encoding="utf-8").write(
        json.dumps([{"term": "стоматологія", "z": 100.0}]))
    run_query_miner(cfg)
    cand = json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())
    assert "стоматологія" not in [c["term"] for c in cand]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_run_query_miner.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `crawler/crawler/learn/run_query_miner.py`:

```python
"""Offline QUERY miner: corpus → service-noun log-odds → soft-stoplist filter →
candidate queue for human audit. Mirror of run_miner, for the query lexicon."""

from crawler.discovery import query_lexicon as ql
from crawler.learn.audit import write_candidates
from crawler.learn.corpus import read_corpus
from crawler.learn.miner import mine
from crawler.learn.tokenize import service_terms
from crawler.learn.query_stoplist import load_blocked, is_suppressed
from crawler.learn.vetoes import survivors


def run_query_miner(config) -> int:
    ql.reload_learned(getattr(config, "query_lexicon_learned_path", None))
    rows = read_corpus(config.corpus_path)
    known = ql.learned_services()
    scores = mine(rows, known_stems=known, stoplist=(), tokenizer=service_terms)
    blocked = load_blocked(config.query_stoplist_path)
    factor = config.query_lexicon_resurface_factor
    scores = [s for s in scores if not is_suppressed(s.term, s.z, blocked, factor)]
    keep = survivors(scores, min_domains=config.query_miner_min_domain_support,
                     min_z=config.query_miner_min_logodds,
                     max_candidates=config.query_miner_max_candidates_per_run)
    write_candidates(config.query_candidates_path, keep)
    return len(keep)


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    import logging

    from crawler.config import load_config

    logging.basicConfig(level=logging.INFO)
    n = run_query_miner(load_config())
    print(f"query candidates written: {n}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_run_query_miner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/run_query_miner.py crawler/tests/test_run_query_miner.py
git commit -m "feat(crawler): run_query_miner (service log-odds + soft stoplist) (B3b)"
```

---

### Task 7: `bootstrap_query_lexicon` orchestrator

**Files:**
- Create: `crawler/crawler/learn/bootstrap_query_lexicon.py`
- Test: `crawler/tests/test_bootstrap_query_lexicon.py`

**Interfaces:**
- Consumes: `api.list_approved_offers(since=None)` (Task 1 supplies `categories`), `CorpusRecorder.record`, `run_query_miner` (Task 6), `query_stoplist.unstop` (Task 5), `RawItem`.
- Produces: `bootstrap(config, api, recorder) -> tuple[int, int]` (categories seeded, candidates written). Seeds category names directly into the LEARNED file (`source="category"`), auto-unstops them, records offer texts into the corpus, then runs `run_query_miner`.

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_bootstrap_query_lexicon.py`:

```python
import json
import types

from crawler.learn.bootstrap_query_lexicon import bootstrap


class _Api:
    def __init__(self, rows): self._rows = rows
    def list_approved_offers(self, since=None):
        assert since is None            # full backfill
        return self._rows


class _Rec:
    def __init__(self): self.texts = []
    def record(self, item, is_offer, *, snowball=False):
        self.texts.append(item.text)


def _cfg(tmp_path):
    return types.SimpleNamespace(
        corpus_path=str(tmp_path / "corpus.jsonl"),
        query_candidates_path=str(tmp_path / "q_cand.json"),
        query_stoplist_path=str(tmp_path / "q_stop.json"),
        query_lexicon_learned_path=str(tmp_path / "q_learned.json"),
        query_miner_min_domain_support=1, query_miner_min_logodds=0.1,
        query_miner_max_candidates_per_run=50, query_lexicon_resurface_factor=2.0)


def test_bootstrap_seeds_categories_and_feeds_corpus(tmp_path):
    cfg = _cfg(tmp_path)
    api = _Api([
        {"text": "Стоматологія Люкс\nзнижка", "host": "a.com", "categories": ["Медицина"]},
        {"text": "Автосервіс\nакція", "host": "b.com", "categories": ["Авто", "Медицина"]},
    ])
    rec = _Rec()
    n_cat, n_cand = bootstrap(cfg, api, rec)
    learned = json.loads(open(cfg.query_lexicon_learned_path, encoding="utf-8").read())
    cats = [e["term"] for e in learned if e.get("source") == "category"]
    assert set(cats) == {"Медицина", "Авто"} and n_cat == 2      # deduped
    assert len(rec.texts) == 2                                    # both offer texts fed
    assert isinstance(n_cand, int)


def test_bootstrap_unstops_a_category(tmp_path):
    cfg = _cfg(tmp_path)
    open(cfg.query_stoplist_path, "w", encoding="utf-8").write(
        json.dumps([{"term": "Медицина", "z": 9.0}]))
    api = _Api([{"text": "x\ny", "host": "a.com", "categories": ["Медицина"]}])
    bootstrap(cfg, api, _Rec())
    stop = json.loads(open(cfg.query_stoplist_path, encoding="utf-8").read())
    assert all(e["term"] != "Медицина" for e in stop)             # auto-unstopped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_bootstrap_query_lexicon.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `crawler/crawler/learn/bootstrap_query_lexicon.py`:

```python
"""One-shot bootstrap: pull ALL approved offers, feed their texts into the corpus,
seed structural offer_categories directly into the LEARNED query lexicon (moderator-
vetted → no audit), then run the text-noun query miner. Idempotent."""

import json
import os
import time

from crawler.learn.query_stoplist import unstop
from crawler.learn.run_query_miner import run_query_miner
from crawler.models import RawItem


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _seed_categories(learned_path, stoplist_path, cats) -> int:
    learned = _load(learned_path, [])
    have = {e.get("term") for e in learned}
    n = 0
    for c in cats:
        unstop(c, stoplist_path)                       # categories > stoplist
        if c not in have:
            learned.append({"term": c, "source": "category",
                            "approved_at": int(time.time())})
            have.add(c)
            n += 1
    _save(learned_path, learned)
    return n


def bootstrap(config, api, recorder) -> tuple[int, int]:
    rows = api.list_approved_offers(since=None) or []
    cats: list[str] = []
    for row in rows:
        item = RawItem(source_id=0, platform="website", key="bootstrap",
                       text=row.get("text", ""),
                       url=f"https://{row.get('host', '')}")
        recorder.record(item, True, snowball=True)
        for c in row.get("categories", []) or []:
            if c and c not in cats:
                cats.append(c)
    n_cat = _seed_categories(config.query_lexicon_learned_path,
                             config.query_stoplist_path, cats)
    n_cand = run_query_miner(config)
    return n_cat, n_cand


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    import logging

    from crawler.config import load_config
    from crawler.learn.corpus import CorpusRecorder
    from crawler.wiring import _build_api_client  # reuse the standard client builder

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    rec = CorpusRecorder(cfg.corpus_path, cfg.corpus_max_mb)
    n_cat, n_cand = bootstrap(cfg, _build_api_client(cfg), rec)
    print(f"seeded categories: {n_cat}; query candidates: {n_cand}")
```

Before writing the `__main__` block, open `crawler/crawler/wiring.py` and confirm the exact helper that constructs the `ApiClient` (it may be named differently than `_build_api_client`). Use the real symbol; if there is no reusable builder, construct `ApiClient` the same way `build_runner` does (same base URL + API key from `config`). The `bootstrap(...)` function itself takes `api` as a parameter and is fully covered by tests — only the CLI wrapper touches wiring.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_bootstrap_query_lexicon.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/bootstrap_query_lexicon.py crawler/tests/test_bootstrap_query_lexicon.py
git commit -m "feat(crawler): bootstrap_query_lexicon (backfill + seed categories) (B3b)"
```

---

### Task 8: Config + wiring integration

**Files:**
- Modify: `crawler/crawler/config.py` (add query-lexicon fields to `_RawSettings` + `Config` + `from_settings`)
- Modify: `crawler/crawler/wiring.py` (reload query_lexicon; pass capped services into `build_grid`)
- Test: `crawler/tests/test_config.py`, `crawler/tests/test_wiring.py`

**Interfaces:**
- Consumes: `query_lexicon` (Task 3), `build_grid(cities, services)` (Task 4).
- Produces: config fields listed in the Interfaces section; wiring builds `grid = QueryGrid(build_grid(cities=<None|[]>, services=<capped learned | []>))`.

- [ ] **Step 1: Write the failing tests**

Add to `crawler/tests/test_config.py` (mirror the file's existing raw/dataclass/default patterns):

```python
def test_query_lexicon_defaults():
    from crawler.config import _RawSettings, Config
    assert _RawSettings().query_lexicon_enabled is True
    assert Config().query_lexicon_max_terms == 40
    assert Config().query_lexicon_resurface_factor == 2.0
```

Add to `crawler/tests/test_wiring.py` (mirror the B3a grid-length tests `test_build_runner_grid_has_cities` / `_disabled` — same active-config factory):

```python
def test_build_runner_grid_includes_learned_services(tmp_path, monkeypatch):
    import crawler.discovery.query_lexicon as ql
    monkeypatch.setattr(ql, "learned_services", lambda: ("стоматологія", "автосервіс"))
    config = _min_active_config(tmp_path, grid_cities_enabled=True,
                                query_lexicon_enabled=True)
    runner = build_runner(config)
    assert len(runner._search_pass._grid) == 1701 + 2 * 6   # two services × 6 audiences


def test_build_runner_query_lexicon_disabled_is_1701(tmp_path, monkeypatch):
    import crawler.discovery.query_lexicon as ql
    monkeypatch.setattr(ql, "learned_services", lambda: ("стоматологія",))
    config = _min_active_config(tmp_path, grid_cities_enabled=True,
                                query_lexicon_enabled=False)
    runner = build_runner(config)
    assert len(runner._search_pass._grid) == 1701           # services suppressed by flag
```

(Use the same factory/`build_runner` symbols the existing wiring tests use; `_min_active_config` must forward the new kwargs — it already forwards arbitrary kwargs into `Config`. `reload_learned` in wiring will overwrite `learned_services`, so patch it AFTER wiring reload by patching the function object as above — if the wiring calls `reload_learned` then `learned_services()`, instead patch `ql.reload_learned` to a no-op AND set the module's returned tuple; simplest: `monkeypatch.setattr(ql, "reload_learned", lambda *_: None)` plus `monkeypatch.setattr(ql, "learned_services", lambda: (...))`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_config.py tests/test_wiring.py -q`
Expected: FAIL — no attribute `query_lexicon_enabled`; grid length mismatch.

- [ ] **Step 3: Add config fields**

In `crawler/crawler/config.py`, add to BOTH `_RawSettings` (near line 79, after `stoplist_path`) and the `Config` dataclass (near line 168), the same block:

```python
    query_lexicon_enabled: bool = True
    query_lexicon_learned_path: str = "/data/query_lexicon_learned.json"
    query_candidates_path: str = "/data/query_candidates.json"
    query_stoplist_path: str = "/data/query_stoplist.json"
    query_lexicon_max_terms: int = 40
    query_lexicon_resurface_factor: float = 2.0
    query_miner_min_domain_support: int = 3
    query_miner_min_logodds: float = 1.5
    query_miner_max_candidates_per_run: int = 50
```

And in `from_settings` (near line 280, after `stoplist_path=s.stoplist_path,`) add:

```python
        query_lexicon_enabled=s.query_lexicon_enabled,
        query_lexicon_learned_path=s.query_lexicon_learned_path,
        query_candidates_path=s.query_candidates_path,
        query_stoplist_path=s.query_stoplist_path,
        query_lexicon_max_terms=s.query_lexicon_max_terms,
        query_lexicon_resurface_factor=s.query_lexicon_resurface_factor,
        query_miner_min_domain_support=s.query_miner_min_domain_support,
        query_miner_min_logodds=s.query_miner_min_logodds,
        query_miner_max_candidates_per_run=s.query_miner_max_candidates_per_run,
```

- [ ] **Step 4: Wire into `build_runner`**

In `crawler/crawler/wiring.py`, change the query-grid import (currently `from crawler.discovery.query_grid import QueryGrid, build_grid`) — it already imports `build_grid` after B3a. Add near the top of the module import group:

```python
from crawler.discovery import query_lexicon
```

Then replace the grid construction inside the `if plans:` block:

```python
        if plans:
            query_lexicon.reload_learned(
                config.query_lexicon_learned_path if config.query_lexicon_enabled else None)
            services = list(query_lexicon.learned_services())[:config.query_lexicon_max_terms]
            cities = None if config.grid_cities_enabled else []
            grid = QueryGrid(build_grid(cities=cities, services=services))
            search_pass = SearchPass(plans, state, grid,
                                     config.search_block_size, config.search_keywords)
            discovery = search_pass.provider_for_site_query()
```

(When `query_lexicon_enabled` is False, `reload_learned(None)` empties the lexicon so `learned_services()` returns `()` ⇒ `services=[]` ⇒ 1701. Byte-eq preserved.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crawler && .venv/Scripts/python -m pytest tests/test_config.py tests/test_wiring.py -q`
Expected: PASS.

- [ ] **Step 6: Run the FULL crawler + backend suites**

Run: `cd crawler && .venv/Scripts/python -m pytest -q` → expect all green (516 + new B3b tests).
Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q` → expect all green.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): wire query_lexicon into build_grid + config flags (B3b)"
```

---

## Self-Review

**Spec coverage:**
- Backend `ApprovedOfferOut.categories` → Task 1. ✓
- Noun tokenizer (`service_terms`) + `mine(tokenizer=)` → Task 2. ✓
- `query_lexicon` consumer (categories-first, z-sorted) → Task 3. ✓
- `build_grid` service block (`{service}{audience}`, 6×N, byte-stable, byte-eq empty) → Task 4. ✓
- Soft non-permanent stoplist + resurface + unstop → Task 5. ✓
- `run_query_miner` (service log-odds, soft-stoplist filter, known=learned) → Task 6. ✓
- `bootstrap_query_lexicon` (full backfill, categories→LEARNED direct, corpus feed, unstop, run miner) → Task 7. ✓
- Config paths/flags/cap/resurface + wiring (reload + capped services + flag byte-eq) → Task 8. ✓
- Cap ordering (categories first, then z) → enforced by `learned_services` (Task 3) + `[:max_terms]` slice (Task 8). ✓
- `audit.approve` reuse for query approve → no code change needed (parameterized by path); operational, exercised in deploy. Not a code task — noted in deploy.

**Placeholder scan:** No TBD/TODO. Each code step has full code. The two "read the existing pattern" notes (Task 7 api-client helper name, Task 8 wiring-test factory) point at concrete sibling code, not vague instructions. ✓

**Type consistency:** `service_terms(text)->list[str]`, `mine(..., tokenizer=)`, `learned_services()->tuple`, `build_grid(cities, services)`, `query_stoplist.{load_blocked,reject,unstop,is_suppressed}`, `run_query_miner(config)->int`, `bootstrap(config,api,recorder)->tuple[int,int]`, config field names — consistent across all tasks and the Interfaces block. ✓

**Ordering:** 1 (backend, independent) → 2,3,4 (independent crawler units) → 5 (stoplist) → 6 (miner, uses 2/3/5) → 7 (bootstrap, uses 6) → 8 (wiring, uses 3/4). Each task's suite stays green independently. ✓
