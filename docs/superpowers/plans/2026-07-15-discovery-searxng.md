# Search Discovery (SearXNG) Implementation Plan — Track B

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-hosted SearXNG service and a best-effort `SearxngProvider`, enabled via `SEARCH_PROVIDERS`, so keyword searches through SearXNG's aggregated engines produce website `SourceCandidate`s in `suggested_sources`.

**Architecture:** A `searxng` compose service (JSON API via a custom `settings.yml`) under the `crawler` profile; a `SearxngProvider` querying `GET /search?format=json`, reusing Track A's `_normalize_url` and the `build_search_provider` dispatch and the `suggested_sources` flow.

**Tech Stack:** `searxng/searxng` Docker image, Python `httpx`, existing crawler discovery stack.

## Global Constraints

- **Off by default**: `SEARCH_PROVIDERS` default stays `duckduckgo`; SearXNG is used only when `searxng` is listed. Service is under `profiles: ["crawler"]` (never on a plain `up`).
- **Best-effort**: any SearXNG error/unavailability/non-JSON logs and returns `[]`; the pass never crashes.
- **Two-stage**: candidates → `suggested_sources` (moderation), not offers.
- **Reuse** Track A's `_normalize_url` and `SourceCandidate` shape (`name/type/url_or_handle/discovered_from_source_id/discovery_note`).
- **SearXNG JSON**: not served by default — the mounted `searxng/settings.yml` must set `search.formats: [html, json]`.
- **Config**: `SEARXNG_URL` (default `http://searxng:8080`), `SEARXNG_SECRET`.
- **Outbound source address unchanged** (`192.168.20.69`); SearXNG adds upstream engine traffic.
- Cross-source dedup (Track C) is OUT of scope.
- Crawler tests run from `crawler/` via `./.venv/Scripts/python.exe -m pytest`.

---

### Task B-1: SearxngProvider + config + combinator (TDD)

**Files:**
- Modify: `crawler/crawler/config.py` (add `searxng_url`)
- Modify: `crawler/crawler/discovery/providers.py` (add `SearxngProvider` + combinator branch)
- Create: `crawler/tests/test_searxng_provider.py`

**Interfaces:**
- Consumes: `_normalize_url` (Track A), `SourceCandidate`.
- Produces: `SearxngProvider(base_url, results_per_keyword=7, min_delay=4.0, client_factory=None, sleep=time.sleep)` — callable `(keyword) -> list[SourceCandidate]`; `Config.searxng_url: str`; `build_search_provider` handles `"searxng"`.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_searxng_provider.py`

```python
import httpx

from crawler.discovery.providers import SearxngProvider, build_search_provider
from types import SimpleNamespace


def _factory(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_searxng_maps_results_to_website_candidates():
    def handler(req):
        assert req.url.path == "/search"
        assert req.url.params["format"] == "json"
        assert req.url.params["q"] == "kw"
        return httpx.Response(200, json={"results": [
            {"url": "https://a.example/x?utm_source=1", "title": "A"},
            {"url": "https://b.example/", "title": "B"},
        ]})
    p = SearxngProvider("http://searxng:8080/", results_per_keyword=5, min_delay=0,
                        client_factory=_factory(handler), sleep=lambda _s: None)
    cands = p("kw")
    assert [c.url_or_handle for c in cands] == ["https://a.example/x", "https://b.example"]
    assert cands[0].type == "website"
    assert cands[0].discovery_note == "searxng: kw"
    assert cands[0].name == "A"


def test_searxng_best_effort_on_http_error():
    def handler(req): return httpx.Response(500)
    p = SearxngProvider("http://searxng:8080", min_delay=0,
                        client_factory=_factory(handler), sleep=lambda _s: None)
    assert p("kw") == []


def test_build_provider_supports_searxng():
    cfg = SimpleNamespace(search_providers=["searxng"], search_results_per_keyword=3,
                          search_min_delay=0, searxng_url="http://searxng:8080")
    assert callable(build_search_provider(cfg))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_searxng_provider.py -q
```
Expected: FAIL — `SearxngProvider` does not exist.

- [ ] **Step 3: Add `searxng_url` to `crawler/crawler/config.py`**

In `_RawSettings`, after the `search_budget` line, add:
```python
    searxng_url: str = "http://searxng:8080"
```
In the `Config` dataclass, after `search_budget`, add:
```python
    searxng_url: str = "http://searxng:8080"
```
In `load_config()`'s `Config(...)`, after `search_budget=(s.search_budget or None),` add:
```python
        searxng_url=s.searxng_url,
```

- [ ] **Step 4: Add `SearxngProvider` to `crawler/crawler/discovery/providers.py`**

Add `import httpx` at the top (with the other imports). Add the class after `DuckDuckGoProvider`:
```python
class SearxngProvider:
    """Callable (keyword) -> list[SourceCandidate]; best-effort, via SearXNG JSON API."""

    def __init__(self, base_url: str, results_per_keyword: int = 7, min_delay: float = 4.0,
                 client_factory=None, sleep=time.sleep):
        self._base = base_url.rstrip("/")
        self._n = results_per_keyword
        self._delay = min_delay
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=20))
        self._sleep = sleep

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        if self._delay:
            self._sleep(self._delay)
        try:
            with self._client_factory() as client:
                resp = client.get(f"{self._base}/search",
                                  params={"q": keyword, "format": "json"})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — search is best-effort
            log.warning("searxng search failed for %r: %s", keyword, exc)
            return []
        out: list[SourceCandidate] = []
        for r in (data.get("results") or [])[:self._n]:
            url = _normalize_url(r.get("url", ""))
            if not url:
                continue
            out.append(SourceCandidate(
                name=r.get("title") or url, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"searxng: {keyword}"))
        return out
```

- [ ] **Step 5: Add the `searxng` branch to `build_search_provider`** in the same file

In the `for name in config.search_providers:` loop, add before the `else:`:
```python
        elif name == "searxng":
            providers.append(SearxngProvider(
                base_url=config.searxng_url,
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay))
```

- [ ] **Step 6: Run tests (new + full suite)**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_searxng_provider.py -q
./.venv/Scripts/python.exe -m pytest -q
```
Expected: new file passes (3 tests); full crawler suite green.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/discovery/providers.py crawler/tests/test_searxng_provider.py
git commit -m "feat(crawler): SearxngProvider + config + combinator branch"
```

---

### Task B-2: SearXNG compose service + settings.yml

**Files:**
- Create: `searxng/settings.yml`
- Modify: `docker-compose.yml` (add `searxng` service; wire crawler `SEARXNG_URL` + depends_on)

**Interfaces:**
- Consumes: `SearxngProvider` reads `http://searxng:8080` (from `SEARXNG_URL`).
- Produces: `searxng` service serving JSON search on internal `:8080`.

- [ ] **Step 1: Create `searxng/settings.yml`**

```yaml
use_default_settings: true
server:
  secret_key: "ultrasecretkey"   # overridden by SEARXNG_SECRET env in the image
  limiter: false                 # internal single-client use; no bot limiter
search:
  formats:
    - html
    - json
```

- [ ] **Step 2: Add the `searxng` service to `docker-compose.yml`** (after the `fixture` service, before `crawler`)

```yaml
  searxng:
    image: searxng/searxng:latest
    profiles: ["crawler"]
    environment:
      SEARXNG_SECRET: ${SEARXNG_SECRET:-changeme-searxng-secret-please-rotate}
    volumes:
      - ./searxng/settings.yml:/etc/searxng/settings.yml:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8080/healthz"]
      interval: 10s
      timeout: 5s
      retries: 12
```

- [ ] **Step 3: Wire the crawler to SearXNG** — in the `crawler` service, change `depends_on` and add `SEARXNG_URL`:

Replace:
```yaml
    depends_on:
      - backend
      - fixture
```
with:
```yaml
    depends_on:
      backend:
        condition: service_started
      fixture:
        condition: service_started
      searxng:
        condition: service_healthy
```
And in the crawler `environment:` block, add:
```yaml
      SEARXNG_URL: http://searxng:8080
```

- [ ] **Step 4: Verify SearXNG builds up and serves JSON**

```bash
docker compose --profile crawler up -d searxng
# wait for healthy, then query JSON from within the network:
docker compose exec -T searxng wget -qO- "http://localhost:8080/search?q=test&format=json" | head -c 200
```
Expected: JSON output containing a `"results"` array (not an HTML page). `docker compose ps` shows `searxng` healthy.

- [ ] **Step 5: Commit**

```bash
git add searxng/settings.yml docker-compose.yml
git commit -m "feat(infra): searxng service (JSON API) under crawler profile"
```

---

### Task B-3: Docs + env example

**Files:**
- Modify: `crawler/.env.example`
- Modify: `README-docker.md`

- [ ] **Step 1: Add SearXNG settings to `crawler/.env.example`**

After the `SEARCH_BUDGET=0` line (before `SEARCH_KEYWORDS`), add:
```dotenv
# SearXNG (Track B): enable by adding `searxng` to SEARCH_PROVIDERS, e.g.
# SEARCH_PROVIDERS=duckduckgo,searxng   (or just: searxng)
SEARXNG_URL=http://searxng:8080
```
Also add to the compose-level env (documented in README): `SEARXNG_SECRET`.

- [ ] **Step 2: Extend the discovery section in `README-docker.md`**

Under the "Search discovery" section, append:
````markdown
### SearXNG (Track B)

A self-hosted metasearch engine that aggregates several upstream engines (more
resilient than a single one). It runs as the `searxng` service under the `crawler`
profile. Enable it by adding `searxng` to `SEARCH_PROVIDERS` (alone or with
`duckduckgo`):

```bash
docker compose --profile crawler up -d searxng        # starts SearXNG
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=searxng crawler
```

Set `SEARXNG_SECRET` in `.env` for a stable secret key. With SearXNG enabled,
outbound traffic (from the same host address `192.168.20.69`) additionally reaches
the upstream engines SearXNG queries (Google/Bing/DuckDuckGo/Brave/Qwant/…).
````

- [ ] **Step 3: Commit**

```bash
git add crawler/.env.example README-docker.md
git commit -m "docs(discovery): SearXNG enablement + outbound note"
```

---

### Task B-4: End-to-end verification (Docker)

**Files:** none (verification).

- [ ] **Step 1: Bring up core + SearXNG**

```bash
docker compose up -d
docker compose --profile crawler up -d searxng
docker compose ps searxng   # expect healthy
```

- [ ] **Step 2: Rebuild crawler (httpx already present; ensure latest code)**

```bash
docker compose build crawler
```

- [ ] **Step 3: Real discovery pass via SearXNG**

```bash
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=searxng -e SEARCH_BUDGET=2 -e SEARCH_MIN_DELAY=2 \
  -e "SEARCH_KEYWORDS=знижки для учасників бойових дій, пільги УБД Україна" \
  crawler 2>&1 | grep -Ei "crawl summary|searxng"
echo "=== suggested from searxng ==="
docker compose exec -T db mysql -uroot -pmy-secret-pw \
  -e "USE ubd; SELECT id, LEFT(url_or_handle,50) AS url, LEFT(CONVERT(note USING utf8mb4),20) AS note FROM suggested_sources WHERE note LIKE 'searxng:%' LIMIT 10;" 2>&1 | grep -v Warning
```
Expected: `crawl summary` with `suggestions > 0`; rows with `note` starting
`searxng:` in `suggested_sources`. If SearXNG's upstreams rate-limit, the pass
still completes (best-effort) — retry or accept `0` as proof of resilience.

- [ ] **Step 4: Confirm in admin**

Open admin (`:8082`) → "Запропоновані джерела" and confirm SearXNG-sourced
candidates (note `searxng: …`) are listed for moderation.

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "test(discovery): verify SearXNG discovery end-to-end"
```

---

## Self-Review

**Spec coverage:**
- `searxng` service under crawler profile, internal 8080, custom settings.yml (JSON) → Task B-2. ✅
- `SearxngProvider` JSON API, best-effort → Task B-1. ✅
- Enable via `SEARCH_PROVIDERS`; combinator branch → Task B-1. ✅
- Reuse `_normalize_url` + `suggested_sources` → Task B-1 (provider) + existing runner. ✅
- Config `SEARXNG_URL`/`SEARXNG_SECRET` → Task B-1 (url) + Task B-2 (secret env). ✅
- Outbound-address doc note → Task B-3. ✅
- Off by default; service unused unless listed → Global Constraints + Task B-1. ✅
- Non-goals (dedup, UI, engine curation) → not implemented. ✅

**Placeholder scan:** No TBD/TODO; every code step has full code; verification steps
give exact commands + expected output; Task B-4 Step 5 uses `--allow-empty`. ✅

**Type consistency:** `SearxngProvider(base_url, results_per_keyword, min_delay,
client_factory, sleep)` matches its construction in `build_search_provider` (Task B-1
Step 5) and tests (Step 1). `config.searxng_url` set in Task B-1 Step 3 is read in
Step 5. `SourceCandidate` fields match `suggestion_payload` and Track A's provider.
`SEARXNG_URL` env (compose, Task B-2 Step 3) maps to `_RawSettings.searxng_url`
(pydantic case-insensitive). SearXNG JSON shape `data["results"][i]["url"]` matches
the provider parsing. ✅
