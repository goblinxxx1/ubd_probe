from crawler.extract.base import get_extractor
from crawler.models import RawItem
from crawler.ratelimit import RateLimiter
from crawler.runner import Runner


class FakeFetcher:
    platform = "website"

    def __init__(self, items):
        self._items = items

    def fetch(self, source, last_seen_key):
        return self._items, "newkey"


class BoomFetcher:
    platform = "telegram"

    def fetch(self, source, last_seen_key):
        raise RuntimeError("boom")


class FakeApi:
    def __init__(self, sources):
        self._sources = sources
        self.offers = []
        self.suggestions = []
        self.state = {}
        self.created = []
        self._offer_cats = []
        self.expired_calls = []

    def list_target_categories(self): return []
    def list_offer_categories(self): return list(self._offer_cats)
    def create_offer_category(self, name, slug):
        row = {"id": 900 + len(self.created), "name": name, "slug": slug}
        self.created.append((name, slug)); self._offer_cats.append(row)
        return row
    def list_sources(self, is_active=True): return self._sources
    def get_crawl_state(self, source_id): return {"last_seen_key": None, "last_crawled_at": None}
    def set_crawl_state(self, source_id, last_seen_key): self.state[source_id] = last_seen_key; return {}
    def submit_offer(self, payload): self.offers.append(payload); return {"id": len(self.offers)}
    def submit_suggestion(self, payload): self.suggestions.append(payload); return {"id": 1}
    def expire_stale(self, older_than_days):
        self.expired_calls.append(older_than_days)
        return {"expired": 2}


def _rl():
    return RateLimiter(min_delay=0, sleep=lambda s: None, monotonic=lambda: 0.0)


def test_runner_submits_offer_and_suggestion_and_state():
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів. Підпишись @newchan", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl())

    summary = runner.run()
    assert summary["offers"] == 1
    assert api.offers[0]["discount_type"] == "percent"
    assert api.offers[0]["content_hash"]
    assert summary["suggestions"] == 1
    assert api.state[1] == "newkey"
    assert summary["errors"] == 0


def test_runner_isolates_source_failure():
    good = {"id": 1, "type": "website", "name": "S1", "url_or_handle": "http://x"}
    bad = {"id": 2, "type": "telegram", "name": "S2", "url_or_handle": "@chan"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Акція 10% для військових", links=[])
    api = FakeApi([bad, good])
    fetchers = {"website": FakeFetcher([item]), "telegram": BoomFetcher()}
    runner = Runner(api, fetchers, get_extractor("heuristic"), _rl())

    summary = runner.run()
    assert summary["errors"] == 1      # telegram source #2 failed
    assert summary["offers"] == 1      # website source #1 still processed


def test_runner_autocreates_offer_category():
    src = {"id": 1, "type": "website", "name": "Барбершоп", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів на стрижку у барбершопі", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl())

    runner.run()
    assert api.created == [("Краса та догляд", "beauty")]
    assert api.offers[0]["offer_category_ids"] == [900]


def test_runner_calls_expire_stale_and_reports_count():
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k", text="Акція 10%", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl(),
                    freshness_ttl_days=14)
    summary = runner.run()
    assert api.expired_calls == [14]
    assert summary["expired"] == 2


from crawler.discovery.walker import WalkPlan
from crawler.models import SourceCandidate


class _MultiPageFetcher:
    """Returns a distinct offer block per URL so we can prove every page is fetched."""
    platform = "website"
    def __init__(self): self.seen = []
    def fetch(self, source, last_seen_key):
        url = source["url_or_handle"]
        self.seen.append(url)
        item = RawItem(source_id=source["id"], platform="website", key=f"k:{url}",
                       text="Знижка 30% для ветеранів", url=url, links=[])
        return [item], f"key:{url}"


class _FakeWalker:
    def __init__(self, urls, domain): self._urls = urls; self._domain = domain
    def walk(self, cand):
        return WalkPlan(domain=self._domain, urls=self._urls, crawl_delay=0.0)


class _FakeDomainRL:
    def __init__(self): self.calls = []
    def wait(self, domain, delay): self.calls.append((domain, delay))


def test_passive_walk_fetches_every_planned_page():
    src = {"id": 7, "type": "website", "name": "Shop", "url_or_handle": "https://shop.ua"}
    api = FakeApi([src])
    fetcher = _MultiPageFetcher()
    walker = _FakeWalker(["https://shop.ua", "https://shop.ua/sale", "https://shop.ua/promo"],
                         "shop.ua")
    drl = _FakeDomainRL()
    runner = Runner(api, {"website": fetcher}, get_extractor("heuristic"), _rl(),
                    walker=walker, domain_rate_limiter=drl)
    summary = runner.run()
    assert fetcher.seen == ["https://shop.ua", "https://shop.ua/sale", "https://shop.ua/promo"]
    assert summary["offers"] == 3                      # one offer per page
    assert drl.calls == [("shop.ua", 0.0)] * 3         # per-domain limiter used
    assert api.state[7] == "key:https://shop.ua/promo" # crawl_state = last page key


def test_passive_walk_skipped_for_telegram_source():
    src = {"id": 8, "type": "telegram", "name": "Chan", "url_or_handle": "https://t.me/chan"}
    api = FakeApi([src])
    item = RawItem(source_id=8, platform="telegram", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    walker = _FakeWalker(["ignored"], "t.me")
    runner = Runner(api, {"telegram": FakeFetcher([item])}, get_extractor("heuristic"), _rl(),
                    walker=walker, domain_rate_limiter=_FakeDomainRL())
    summary = runner.run()
    assert summary["offers"] == 1                       # normal single-fetch path


class _OneBadPageFetcher:
    """Raises on one URL, returns an offer block on the others."""
    platform = "website"
    def __init__(self, bad_url): self._bad = bad_url; self.seen = []
    def fetch(self, source, last_seen_key):
        url = source["url_or_handle"]
        self.seen.append(url)
        if url == self._bad:
            raise RuntimeError("boom page")
        item = RawItem(source_id=source["id"], platform="website", key=f"k:{url}",
                       text="Знижка 30% для ветеранів", url=url, links=[])
        return [item], f"key:{url}"


def test_passive_walk_one_bad_page_does_not_abort_domain():
    src = {"id": 9, "type": "website", "name": "Shop", "url_or_handle": "https://shop.ua"}
    api = FakeApi([src])
    fetcher = _OneBadPageFetcher("https://shop.ua/sale")   # middle page blows up
    walker = _FakeWalker(["https://shop.ua", "https://shop.ua/sale", "https://shop.ua/promo"],
                         "shop.ua")
    runner = Runner(api, {"website": fetcher}, get_extractor("heuristic"), _rl(),
                    walker=walker, domain_rate_limiter=_FakeDomainRL())
    summary = runner.run()
    assert fetcher.seen == ["https://shop.ua", "https://shop.ua/sale", "https://shop.ua/promo"]
    assert summary["offers"] == 2                       # first + third still processed
    assert summary["errors"] == 1                       # the bad page counted once
    assert api.state[9] == "key:https://shop.ua/promo"  # walk continued to the last page


from crawler.discovery.domain_registry import DomainRegistry


class _RecordingHarvester:
    def __init__(self): self.candidates = None; self.known_hosts = None
    def harvest(self, candidates, cats, known, summary, known_hosts=None):
        self.candidates = list(candidates); self.known_hosts = set(known_hosts or set())


class _StubFeed:
    def __init__(self, cands): self._cands = cands
    def candidates(self, known_hosts):
        return [c for c in self._cands if c.name not in known_hosts]


def test_active_block_prepends_domain_feed_and_builds_known_hosts(tmp_path):
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    feed_cand = SourceCandidate(name="proven.ua", type="website",
                                url_or_handle="https://proven.ua")
    hv = _RecordingHarvester()
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, domain_feed=_StubFeed([feed_cand]), domain_registry=reg)
    runner.run()
    assert hv.candidates[0].url_or_handle == "https://proven.ua"   # feed first (exploit)
    assert hv.known_hosts == {"silpo.ua"}                          # active source host


def test_active_host_skip_is_unconditional():
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    hv = _RecordingHarvester()
    # rating OFF (no domain_feed/registry) — host-skip of active-source hosts STILL applies,
    # so active never crawls a published/approved source.
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, brand_feed=_StubFeed([SourceCandidate(
                        name="x.ua", type="website", url_or_handle="https://x.ua")]))
    runner.run()
    assert hv.known_hosts == {"silpo.ua"}


def test_active_block_prunes_and_saves_registry(tmp_path):
    import os
    p = str(tmp_path / "r.json")
    api = FakeApi([])
    reg = DomainRegistry(p, clock=lambda: 1e9)
    reg.record("dead.ua", offers=0, errors=1)          # score 0, old (last_seen 1e9, ttl small)
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), domain_feed=_StubFeed([]),
                    domain_registry=reg, domain_evict_min_score=0.1,
                    domain_evict_ttl_seconds=0.0)
    runner.run()
    assert os.path.exists(p)                            # saved
    assert DomainRegistry.load(p).top(10, set()) == [] # dead pruned


from crawler.discovery.search_state import SearchState
from crawler.discovery.site_query import SiteQueryPlanner


class _MutatingDiscovery:
    """Records each keyword list passed; returns one candidate per call."""
    def __init__(self): self.calls = []
    def run(self, keywords, known):
        self.calls.append(list(keywords))
        return [SourceCandidate(name="site", type="website",
                                url_or_handle="https://proven.ua/promo")]


def test_site_query_block_uses_registry_only_not_approved(tmp_path):
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    reg.record("proven.ua", offers=2, errors=0)          # productive, non-approved
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: 1.0)
    disc = _MutatingDiscovery()
    hv = _RecordingHarvester()
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, discovery=disc, domain_registry=reg,
                    site_planner=SiteQueryPlanner(terms=("знижка", "акція")),
                    site_state=state, site_query_budget=5)
    runner.run()

    site_qs = disc.calls[-1]
    assert any(q.startswith("site:proven.ua") for q in site_qs)   # productive domain queried
    assert not any("silpo.ua" in q for q in site_qs)              # approved source NOT site-queried
    assert hv.candidates and all(c.bypass_host_skip for c in hv.candidates)
    assert SearchState.load(str(tmp_path / "s.json")).site_cursor == 1   # advanced & persisted


def test_approved_sources_never_site_queried(tmp_path):
    srcs = [{"id": i, "type": "website", "name": h, "url_or_handle": f"https://{h}"}
            for i, h in enumerate(["a.ua", "b.ua", "c.ua", "d.ua"], start=1)]
    api = FakeApi(srcs)
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)   # empty registry
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: 1.0)
    disc = _MutatingDiscovery()
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), discovery=disc, domain_registry=reg,
                    site_planner=SiteQueryPlanner(terms=("t1", "t2")),
                    site_state=state, site_query_budget=2)
    for _ in range(3):
        runner.run()
    hosts = {q.split()[0].removeprefix("site:") for qlist in disc.calls for q in qlist}
    assert hosts.isdisjoint({"a.ua", "b.ua", "c.ua", "d.ua"})   # active never site-queries approved sources


def test_site_query_off_is_byte_equivalent(tmp_path):
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    reg.record("proven.ua", offers=2, errors=0)
    disc = _MutatingDiscovery()
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), discovery=disc, domain_registry=reg,
                    domain_feed=_StubFeed([]),
                    site_planner=None, site_state=None)   # lever off
    runner.run()
    assert disc.calls == []                               # no site queries issued


class _StubOsm:
    def __init__(self, cands): self._cands = cands
    def candidates(self, known): return list(self._cands)


def test_runner_unions_osm_feed_candidates():
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    hv = _RecordingHarvester()
    osm_cand = SourceCandidate(name="Foo", type="website", url_or_handle="https://foo.ua")
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, osm_feed=_StubOsm([osm_cand]))
    runner.run()
    assert any(c.url_or_handle == "https://foo.ua" for c in hv.candidates)


def test_runner_interleaves_feeds_round_robin():
    src = {"id": 1, "type": "website", "name": "S", "url_or_handle": "https://s.ua"}
    api = FakeApi([src])
    hv = _RecordingHarvester()
    df = _StubFeed([SourceCandidate(name="d1", type="website", url_or_handle="https://d1.ua"),
                    SourceCandidate(name="d2", type="website", url_or_handle="https://d2.ua")])
    of = _StubOsm([SourceCandidate(name="o1", type="website", url_or_handle="https://o1.ua"),
                   SourceCandidate(name="o2", type="website", url_or_handle="https://o2.ua")])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, domain_feed=df, domain_registry=None, osm_feed=of)
    runner.run()
    names = [c.name for c in hv.candidates]
    assert names == ["d1", "o1", "d2", "o2"]   # round-robin: domain, osm, domain, osm


class _StubAgg:
    def __init__(self, cands): self._cands = cands
    def candidates(self, known): return list(self._cands)


def test_runner_unions_aggregator_feed_candidates():
    src = {"id": 1, "type": "website", "name": "S", "url_or_handle": "https://s.ua"}
    api = FakeApi([src])
    hv = _RecordingHarvester()
    cand = SourceCandidate(name="biz.ua", type="website", url_or_handle="https://biz.ua")
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, aggregator_feed=_StubAgg([cand]))
    runner.run()
    assert any(c.url_or_handle == "https://biz.ua" for c in hv.candidates)


from crawler.schedule import PassiveSchedule


def _ubd_item():
    return RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів", links=[])


def test_run_active_does_not_crawl_sources_or_expire():
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "https://shop.ua"}
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester())
    runner.run_active()
    assert api.state == {}            # no source crawled (passive path untouched)
    assert api.expired_calls == []    # no expiry in the active pass


def test_run_passive_crawls_sources_and_expires():
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([_ubd_item()])}, get_extractor("heuristic"), _rl())
    summary = runner.run_passive()
    assert api.state[1] == "newkey"   # source crawled
    assert api.expired_calls == [30]  # default TTL swept
    assert summary["offers"] == 1


def test_run_active_first_then_passive_when_due():
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "https://s.ua"}])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl())
    order = []
    runner.run_active = lambda: (order.append("active"), runner._empty_summary())[1]
    runner.run_passive = lambda: (order.append("passive"), runner._empty_summary())[1]
    runner.run()
    assert order == ["active", "passive"]


def test_passive_skipped_when_not_due(tmp_path):
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "http://x"}])
    sched = PassiveSchedule(str(tmp_path / "p.json"), 10_000, now=lambda: 1000.0)
    sched.mark()   # just marked → not due
    runner = Runner(api, {"website": FakeFetcher([_ubd_item()])}, get_extractor("heuristic"), _rl(),
                    passive_schedule=sched)
    runner.run()
    assert api.state == {}            # passive did NOT run
    assert api.expired_calls == []


def test_passive_runs_when_due_and_marks(tmp_path):
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "http://x"}])
    p = str(tmp_path / "p.json")
    sched = PassiveSchedule(p, 10_000, now=lambda: 1000.0)   # no file → due
    runner = Runner(api, {"website": FakeFetcher([_ubd_item()])}, get_extractor("heuristic"), _rl(),
                    passive_schedule=sched)
    runner.run()
    assert api.state[1] == "newkey"   # passive ran
    assert PassiveSchedule(p, 10_000, now=lambda: 1000.0).due() is False   # cadence marked


def test_run_without_schedule_runs_both():
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "http://x"}])
    runner = Runner(api, {"website": FakeFetcher([_ubd_item()])}, get_extractor("heuristic"), _rl())
    runner.run()
    assert api.state[1] == "newkey"    # passive ran (backward compat)
    assert api.expired_calls == [30]


def test_site_query_excludes_blocklisted_registry_hosts(tmp_path):
    from crawler.discovery import blocklist
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "http://x"}])
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    reg.record("proven.ua", offers=3, errors=0)    # productive, allowed
    reg.record("badnews.ua", offers=3, errors=0)   # productive, blocklisted
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: 1.0)
    disc = _MutatingDiscovery()
    blocklist.reload_learned(["badnews.ua"])
    try:
        runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                        harvester=_RecordingHarvester(), discovery=disc, domain_registry=reg,
                        site_planner=SiteQueryPlanner(terms=("знижка",)),
                        site_state=state, site_query_budget=5)
        runner.run_active()
    finally:
        blocklist.reload_learned(None)
    qs = " ".join(q for call in disc.calls for q in call)
    assert "proven.ua" in qs
    assert "badnews.ua" not in qs


def test_site_query_pool_respects_revisit_cooldown(tmp_path):
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "http://x"}])
    t = {"v": 1000.0}
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: t["v"])
    reg.record("proven.ua", offers=3, errors=0)   # seen at 1000
    t["v"] = 1000.0 + 10
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: 1.0)
    disc = _MutatingDiscovery()
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), discovery=disc, domain_registry=reg,
                    site_planner=SiteQueryPlanner(terms=("знижка",)),
                    site_state=state, site_query_budget=5, revisit_cooldown_seconds=100)
    runner.run_active()
    qs = " ".join(q for call in disc.calls for q in call)
    assert "proven.ua" not in qs


class _OrderFeed:
    def __init__(self, log): self._log = log
    def candidates(self, known_hosts):
        self._log.append("feed"); return []


class _OrderIngestor:
    def __init__(self, log): self._log = log; self.calls = 0
    def ingest(self): self._log.append("ingest"); self.calls += 1; return 0


class _BoomIngestor:
    def ingest(self): raise RuntimeError("reject boom")


def test_run_active_ingests_rejections_before_feeds():
    api = FakeApi([])
    order = []
    ing = _OrderIngestor(order)
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), domain_feed=_OrderFeed(order),
                    reject_ingestor=ing)
    runner.run()
    assert ing.calls == 1
    assert order[0] == "ingest" and "feed" in order   # ingest ran before the feed


def test_run_active_survives_reject_ingest_error():
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), domain_feed=_StubFeed([]),
                    reject_ingestor=_BoomIngestor())
    summary = runner.run()                      # must not raise
    assert summary["errors"] >= 1               # error counted, pass completed


def test_run_active_no_ingestor_is_fine():
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), domain_feed=_StubFeed([]))
    runner.run()                                # no reject_ingestor → no crash


def test_learn_and_reload_grid_mines_then_swaps_live_grid(monkeypatch):
    from types import SimpleNamespace
    calls = {}
    monkeypatch.setattr("crawler.learn.bootstrap_query_lexicon.bootstrap",
                        lambda cfg, api, rec: calls.setdefault("boot", (cfg, api, rec)))
    monkeypatch.setattr("crawler.wiring.build_query_grid", lambda cfg: "FRESH_GRID")

    class _SP:
        def __init__(self): self.grid = None
        def set_grid(self, g): self.grid = g

    sp, api, corpus = _SP(), FakeApi([]), object()
    runner = Runner(api, {}, get_extractor("heuristic"), _rl(),
                    search_pass=sp, corpus_recorder=corpus)
    cfg = SimpleNamespace(corpus_path="x", corpus_max_mb=1)
    runner.learn_and_reload_grid(cfg)
    assert calls["boot"] == (cfg, api, corpus)   # mined with runner's own api + corpus
    assert sp.grid == "FRESH_GRID"               # freshly rebuilt grid swapped in live


def test_learn_and_reload_grid_noop_without_search_pass(monkeypatch):
    from types import SimpleNamespace
    boot = []
    monkeypatch.setattr("crawler.learn.bootstrap_query_lexicon.bootstrap",
                        lambda *a, **k: boot.append(1))
    runner = Runner(FakeApi([]), {}, get_extractor("heuristic"), _rl(), search_pass=None)
    runner.learn_and_reload_grid(SimpleNamespace(corpus_path="x", corpus_max_mb=1))
    assert boot == []   # no active search pass → nothing to learn or reload


def test_run_active_marks_only_fully_consumed_search_phrases():
    from crawler.models import SourceCandidate
    marked = {}
    class _State:
        def mark_harvested(self, ks): marked["ks"] = list(ks)
    class _SP:
        _state = _State()
        def run(self, known):
            return [SourceCandidate(name="a1", type="website", url_or_handle="https://a1.ua", origin_key="phraseA"),
                    SourceCandidate(name="a2", type="website", url_or_handle="https://a2.ua", origin_key="phraseA"),
                    SourceCandidate(name="b1", type="website", url_or_handle="https://b1.ua", origin_key="phraseB")]
        def provider_for_site_query(self): return None
    class _Harv:
        def harvest(self, candidates, cats, known, summary, known_hosts=None):
            return 2                      # examined first 2 (both phraseA); stopped before phraseB
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_Harv(), search_pass=_SP())
    runner.run_active()
    assert marked["ks"] == ["phraseA"]    # phraseB straddles the budget -> NOT marked


class _EmptyFetcher:
    """Website fetcher that never yields an offer-bearing item (an empty pass)."""
    platform = "website"
    def __init__(self): self.calls = 0
    def fetch(self, source, last_seen_key):
        self.calls += 1
        return [], last_seen_key


def test_passive_skips_source_for_next_crawls_after_empty_pass(tmp_path):
    src = {"id": 11, "type": "website", "name": "Empty", "url_or_handle": "https://empty.ua"}
    api = FakeApi([src])
    fetcher = _EmptyFetcher()
    walker = _FakeWalker(["https://empty.ua"], "empty.ua")
    reg = DomainRegistry(str(tmp_path / "r.json"), empty_skip=5)
    runner = Runner(api, {"website": fetcher}, get_extractor("heuristic"), _rl(),
                    walker=walker, domain_rate_limiter=_FakeDomainRL(), domain_registry=reg)
    runner.run_passive()
    assert fetcher.calls == 1                 # crawled once, found nothing -> skip armed
    runner.run_passive()
    runner.run_passive()
    assert fetcher.calls == 1                 # skipped on the following passes


def test_passive_does_not_skip_a_productive_source(tmp_path):
    src = {"id": 12, "type": "website", "name": "Shop", "url_or_handle": "https://shop.ua"}
    api = FakeApi([src])
    fetcher = _MultiPageFetcher()             # yields an offer per page
    walker = _FakeWalker(["https://shop.ua"], "shop.ua")
    reg = DomainRegistry(str(tmp_path / "r.json"), empty_skip=5)
    runner = Runner(api, {"website": fetcher}, get_extractor("heuristic"), _rl(),
                    walker=walker, domain_rate_limiter=_FakeDomainRL(), domain_registry=reg)
    runner.run_passive()
    runner.run_passive()
    assert fetcher.seen == ["https://shop.ua", "https://shop.ua"]   # crawled both passes


def _inline_executor_factory(max_workers):
    """Детермінований замінник ThreadPoolExecutor: виконує кожну submit-задачу
    синхронно одразу при виклику, щоб тестувати логіку run_passive без реальних гонок."""
    from concurrent.futures import Future

    class _Inline:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def submit(self, fn, *a, **kw):
            f = Future()
            f.set_result(fn(*a, **kw))
            return f
    return _Inline()


def test_run_passive_parallel_sums_summary_across_sources():
    srcs = [{"id": i, "type": "website", "name": f"S{i}",
             "url_or_handle": f"http://x{i}"} for i in range(3)]
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    api = FakeApi(srcs)
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"),
                    _rl(), passive_workers=3,
                    executor_factory=_inline_executor_factory)
    summary = runner.run_passive()
    assert summary["offers"] == 3         # one offer per source, all merged
    assert summary["sources"] == 3
    assert summary["errors"] == 0
    assert summary["expired"] == 2        # expire_stale still runs once, after join


def test_run_passive_parallel_isolates_source_failure():
    good = {"id": 1, "type": "website", "name": "S1", "url_or_handle": "http://x"}
    bad = {"id": 2, "type": "telegram", "name": "S2", "url_or_handle": "@chan"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Акція 10% для військових", links=[])
    api = FakeApi([bad, good])
    fetchers = {"website": FakeFetcher([item]), "telegram": BoomFetcher()}
    runner = Runner(api, fetchers, get_extractor("heuristic"), _rl(),
                    passive_workers=2, executor_factory=_inline_executor_factory)
    summary = runner.run_passive()
    assert summary["errors"] == 1
    assert summary["offers"] == 1


def test_run_passive_workers_1_is_serial_baseline():
    srcs = [{"id": i, "type": "website", "name": f"S{i}",
             "url_or_handle": f"http://x{i}"} for i in range(3)]
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    api = FakeApi(srcs)
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"),
                    _rl(), passive_workers=1)   # real ThreadPoolExecutor(max_workers=1)
    summary = runner.run_passive()
    assert summary["offers"] == 3
    assert summary["sources"] == 3
    assert summary["errors"] == 0


def test_passive_gate_drops_non_genuine():
    class DropGate:
        def keep(self, cand): return False
        def reset_breaker(self): pass
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl(),
                    relevance_gate=DropGate())
    summary = runner.run()
    assert summary["offers"] == 0             # гейт відкинув


def test_saturation_gauge_is_logged(caplog):
    # coverage_counts -> observed=4,f1=2,f2=1 -> chao1=4+(2*2)/(2*1)=6 -> saturation=4/6~=0.667
    # (перевірено виконанням: brief-приклад ~0.714 не збігається з фактичною формулою chao1;
    # цей тест гарантує формулу, яку runner логує; wiring-тест нижче ловить сам рядок логу)
    from crawler.discovery.coverage import saturation as sat
    pct = sat(4, 2, 1)
    assert 0.665 < pct < 0.668     # guards the formula the runner will log


def test_run_active_logs_coverage_saturation_gauge(caplog):
    class _CovState:
        def coverage_counts(self): return (4, 2, 1)   # -> chao1=6 -> saturation=4/6~=66.7%
    class _SP:
        _state = _CovState()
        def run(self, known): return []
        def provider_for_site_query(self): return None
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), search_pass=_SP())
    with caplog.at_level("INFO", logger="crawler.runner"):
        runner.run_active()
    msgs = [r.getMessage() for r in caplog.records if r.name == "crawler.runner"]
    assert "active coverage: observed=4 saturation=66.7%" in msgs


def test_run_active_logs_productivity_metric(caplog):
    """Задача 8: саморозказаний продуктивність-гейдж — не потрібен ручний аналіз,
    лише grep 'active productivity' по логах (48h wiring перевіряється тут)."""
    class _CovState:
        def coverage_counts(self): return (4, 2, 1)   # -> saturation=66.7%
    class _SP:
        _state = _CovState()
        def run(self, known): return []
        def provider_for_site_query(self): return None
        def last_productivity(self): return (3, 5)    # 3 нових домени за 5 запитів
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), search_pass=_SP())
    with caplog.at_level("INFO", logger="crawler.runner"):
        runner.run_active()
    msgs = [r.getMessage() for r in caplog.records if r.name == "crawler.runner"]
    assert ("active productivity: new_domains=3 / queries=5 (0.60 new/query) "
            "| saturation=66.7%") in msgs


def test_run_active_skips_productivity_log_when_search_pass_lacks_accessor():
    """Existing fakes without last_productivity() must not crash run_active
    (guarded, back-compat with pre-Задача-8 test doubles)."""
    class _CovState:
        def coverage_counts(self): return (4, 2, 1)
    class _SP:
        _state = _CovState()
        def run(self, known): return []
        def provider_for_site_query(self): return None
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), search_pass=_SP())
    summary = runner.run_active()          # no last_productivity() -> guarded, no crash
    assert summary["errors"] == 0


def test_run_active_skips_productivity_log_on_drain_path(caplog):
    """ddg_allowed=False means SearchPass.drain() ran, not run() — last_productivity()
    would be stale/carried over from a previous cycle, so the productivity log must
    not fire for this cycle at all."""
    class _CovState:
        def coverage_counts(self): return (4, 2, 1)
    class _SP:
        _state = _CovState()
        def drain(self): return []
        def provider_for_site_query(self): return None
        def last_productivity(self): return (99, 1)   # stale value from a prior cycle
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), search_pass=_SP())
    with caplog.at_level("INFO", logger="crawler.runner"):
        runner.run_active(ddg_allowed=False)
    msgs = [r.getMessage() for r in caplog.records if r.name == "crawler.runner"]
    assert not any("active productivity" in m for m in msgs)


def test_run_active_skips_coverage_log_when_state_lacks_coverage_counts():
    """Existing fakes (e.g. mark_harvested-only _state) must not crash run_active."""
    class _State:
        def mark_harvested(self, ks): pass
    class _SP:
        _state = _State()
        def run(self, known): return []
        def provider_for_site_query(self): return None
    api = FakeApi([])
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), search_pass=_SP())
    summary = runner.run_active()          # no coverage_counts() -> guarded, no crash
    assert summary["errors"] == 0
