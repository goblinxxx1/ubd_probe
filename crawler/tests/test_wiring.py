from crawler.config import Config
from crawler.extract.base import CategoryIndex
from crawler.models import RawItem
from crawler.wiring import build_runner


def test_build_runner_wires_all_platforms():
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, osm_feed_enabled=False,
    )
    runner = build_runner(cfg)
    assert set(runner._fetchers.keys()) == {"website", "telegram", "instagram", "facebook"}
    # extractor is the heuristic one (returns None on non-offer text)
    assert runner._extractor.extract(RawItem(1, "website", "k", ""), "P",
                                     CategoryIndex([], [])) is None


def test_build_runner_wires_require_discount():
    from crawler.config import Config
    from crawler.wiring import build_runner
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        require_discount=True,
    )
    runner = build_runner(cfg)
    assert runner._extractor._require_discount is True


from crawler.discovery.search_state import SearchState


def test_build_runner_no_build_time_cursor_advance(tmp_path):
    state_path = str(tmp_path / "state.json")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=True, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        search_providers=[],                 # no providers -> no plans, no SearchPass
        search_keywords=["мій пін"],
        search_state_path=state_path,
        brand_feed_enabled=False, osm_feed_enabled=False,
    )
    runner = build_runner(cfg)
    assert runner._search_pass is None
    assert SearchState.load(state_path).grid_cursor == 0    # cursor advances at RUN, not BUILD


import json

from crawler.discovery.brand_feed import BrandFeed
from crawler.runner import Runner
from crawler.models import SourceCandidate


def test_build_runner_brand_feed_runs_without_ddg(tmp_path):
    # Pre-write a FRESH cache (far-future refreshed_at) so build_runner does NOT refresh
    # (no network), and points brand_domains_path at tmp (not /data).
    bpath = tmp_path / "brand_domains.json"
    bpath.write_text(json.dumps({"version": 1, "refreshed_at": 9_999_999_999.0,
                                 "domains": {"OKKO": "okko.ua"}}), encoding="utf-8")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=True,
        brand_domains_path=str(bpath),
        brand_feed_refresh_hours=336,
        active_fetch_budget=20,
        osm_feed_enabled=False,
    )
    runner = build_runner(cfg)
    assert runner._discovery is None
    assert isinstance(runner._brand_feed, BrandFeed)
    assert runner._harvester is not None


def test_runner_unions_brand_feed_and_ddg_candidates():
    class _Api:
        def list_target_categories(self):
            return []

        def list_offer_categories(self):
            return []

        def list_sources(self, is_active=True):
            return []

        def expire_stale(self, days):
            return {"expired": 0}

    class _SearchPass:
        def run(self, known):
            return [SourceCandidate(name="ddg", type="website",
                                    url_or_handle="https://ddg.example")]
        def provider_for_site_query(self): return None

    class _Feed:
        def candidates(self, known):
            return [SourceCandidate(name="OKKO", type="website",
                                    url_or_handle="https://okko.ua")]

    class _Harvester:
        def __init__(self):
            self.seen = None

        def harvest(self, candidates, cats, known, summary, known_hosts=None):
            self.seen = list(candidates)

    harv = _Harvester()
    runner = Runner(_Api(), {}, extractor=None, rate_limiter=None,
                    search_pass=_SearchPass(), harvester=harv,
                    brand_feed=_Feed())
    runner.run()
    assert {c.name for c in harv.seen} == {"ddg", "OKKO"}


def test_runner_skips_harvest_when_no_candidates():
    class _Api:
        def list_target_categories(self):
            return []

        def list_offer_categories(self):
            return []

        def list_sources(self, is_active=True):
            return []

        def expire_stale(self, days):
            return {"expired": 0}

    class _EmptySearchPass:
        def run(self, known): return []
        def provider_for_site_query(self): return None

    class _Harvester:
        def __init__(self):
            self.called = False

        def harvest(self, candidates, cats, known, summary):
            self.called = True

    harv = _Harvester()
    runner = Runner(_Api(), {}, extractor=None, rate_limiter=None,
                    search_pass=_EmptySearchPass(), harvester=harv,
                    brand_feed=None)
    runner.run()
    assert harv.called is False


from crawler.discovery.walker import DomainWalker


def _harvest_config(tmp_path, **over):
    bpath = tmp_path / "brand_domains.json"
    bpath.write_text(json.dumps({"version": 1, "refreshed_at": 9_999_999_999.0,
                                 "domains": {"OKKO": "okko.ua"}}), encoding="utf-8")
    base = dict(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=True, brand_domains_path=str(bpath),
        brand_feed_refresh_hours=336, active_fetch_budget=20,
        robots_cache_path=str(tmp_path / "robots.json"),
        osm_feed_enabled=False,
    )
    base.update(over)
    return Config(**base)


def test_walker_built_when_sitemap_depth_enabled(tmp_path):
    runner = build_runner(_harvest_config(tmp_path, sitemap_depth_enabled=True))
    assert isinstance(runner._harvester._walker, DomainWalker)
    assert runner._harvester._domain_rl is not None


def test_no_walker_when_sitemap_depth_disabled(tmp_path):
    # domain_rating_enabled=False here too: its default (True) independently builds a
    # walker for passive deep-walk, which is exercised by the domain-rating tests below.
    runner = build_runner(_harvest_config(tmp_path, sitemap_depth_enabled=False,
                                          domain_rating_enabled=False))
    assert runner._harvester._walker is None


def test_build_runner_autofill_off_has_no_recorder():
    cfg = Config(internal_api_url="http://x", crawler_api_key="k", extractor="heuristic",
                 active_discovery=False, request_timeout=1.0, min_delay_seconds=1.0,
                 autofill_enabled=False, brand_feed_enabled=False,
                 sitemap_depth_enabled=False, osm_feed_enabled=False)
    r = build_runner(cfg)
    assert r._corpus is None


def test_domain_rating_off_is_byte_equivalent(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False,
        domain_rating_enabled=False, osm_feed_enabled=False,
    )
    runner = build_runner(cfg)
    assert runner._domain_feed is None
    assert runner._domain_registry is None
    assert runner._walker is None


def test_domain_rating_on_builds_feed_registry_and_walker(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=True,   # brand_feed off → no network
        domain_rating_enabled=True, osm_feed_enabled=False,
        domain_registry_path=str(tmp_path / "reg.json"),
        robots_cache_path=str(tmp_path / "robots.json"),
    )
    runner = build_runner(cfg)
    assert runner._domain_feed is not None
    assert runner._domain_registry is not None
    assert runner._walker is not None                 # passive deep-walk enabled


def test_domain_rating_on_without_sitemap_builds_walker(tmp_path):
    # covers the wiring branch `if walker is None: walker, domain_rl = _build_walker(...)`:
    # domain-rating alone (sitemap_depth off) must still build a walker for passive deep-walk.
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False,
        domain_rating_enabled=True, osm_feed_enabled=False,
        domain_registry_path=str(tmp_path / "reg.json"),
        robots_cache_path=str(tmp_path / "robots.json"),
    )
    runner = build_runner(cfg)
    assert runner._walker is not None                 # built by the domain-rating branch
    assert runner._domain_registry is not None


def test_build_runner_reloads_blocked_hosts(monkeypatch, tmp_path):
    import crawler.wiring as w
    from crawler.discovery import blocklist
    captured = {}
    monkeypatch.setattr(blocklist, "reload_learned",
                        lambda hosts: captured.setdefault("hosts", hosts))
    # make ApiClient.list_blocked_hosts return a fixed set without network
    monkeypatch.setattr(w.ApiClient, "list_blocked_hosts",
                        lambda self: ["learned.example"], raising=False)
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False, domain_rating_enabled=False,
        osm_feed_enabled=False,
        blocked_hosts_fetch_enabled=True,
    )
    w.build_runner(cfg)
    assert captured["hosts"] == ["learned.example"]


def test_build_runner_blocked_hosts_fetch_best_effort(monkeypatch):
    import crawler.wiring as w
    def boom(self): raise RuntimeError("net down")
    monkeypatch.setattr(w.ApiClient, "list_blocked_hosts", boom, raising=False)
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False, domain_rating_enabled=False,
        osm_feed_enabled=False,
        blocked_hosts_fetch_enabled=True,
    )
    w.build_runner(cfg)   # must not raise


def test_build_runner_wires_passive_schedule(monkeypatch, tmp_path):
    import crawler.wiring as w
    from crawler.schedule import PassiveSchedule
    monkeypatch.setattr(w.ApiClient, "list_blocked_hosts", lambda self: [], raising=False)
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False, domain_rating_enabled=False,
        osm_feed_enabled=False,
        passive_interval_seconds=345600,
        passive_state_path=str(tmp_path / "passive.json"),
    )
    runner = w.build_runner(cfg)
    assert isinstance(runner._passive_schedule, PassiveSchedule)
    assert runner._passive_schedule._interval == 345600


from crawler.discovery.site_query import SiteQueryPlanner


def _base_cfg(tmp_path, **kw):
    defaults = dict(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        request_timeout=5.0, min_delay_seconds=0.0, bot_accounts=[], proxies={},
        search_providers=[], search_state_path=str(tmp_path / "state.json"),
        brand_feed_enabled=False, osm_feed_enabled=False,
        domain_registry_path=str(tmp_path / "r.json"))
    defaults.update(kw)
    return Config(**defaults)


def test_build_runner_wires_site_query_lever(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=True, site_query_enabled=True,
                    site_query_budget=7, domain_rating_enabled=True)
    runner = build_runner(cfg)
    assert isinstance(runner._site_planner, SiteQueryPlanner)
    assert runner._site_state is not None            # active_discovery on → shared state
    assert runner._site_query_budget == 7


def test_build_runner_site_query_disabled(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=True, site_query_enabled=False)
    runner = build_runner(cfg)
    assert runner._site_planner is None


def test_build_runner_site_state_none_without_active_discovery(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=False, site_query_enabled=True)
    runner = build_runner(cfg)
    assert runner._site_planner is not None
    assert runner._site_state is None                # no active search → no state to rotate


import json as _json_osm

from crawler.discovery.osm_feed import OsmDomainFeed


def test_build_runner_osm_feed_runs_without_network(tmp_path):
    # FRESH cache (far-future refreshed_at) so build_runner does NOT hit Overpass.
    opath = tmp_path / "osm_domains.json"
    opath.write_text(_json_osm.dumps({"version": 1, "refreshed_at": 9_999_999_999.0,
                                      "domains": {"Foo": "foo.ua"}, "cursor": 0}),
                     encoding="utf-8")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False,
        osm_feed_enabled=True, osm_domains_path=str(opath), osm_feed_refresh_hours=336)
    runner = build_runner(cfg)
    assert isinstance(runner._osm_feed, OsmDomainFeed)


def test_build_runner_osm_feed_disabled(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False, osm_feed_enabled=False)
    runner = build_runner(cfg)
    assert runner._osm_feed is None


def test_build_runner_osm_only_still_builds_harvester(tmp_path):
    import json as _json_osm2
    opath = tmp_path / "osm_domains.json"
    opath.write_text(_json_osm2.dumps({"version": 1, "refreshed_at": 9_999_999_999.0,
                                       "domains": {"Foo": "foo.ua"}, "cursor": 0}),
                     encoding="utf-8")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False,
        domain_rating_enabled=False, osm_feed_enabled=True,
        osm_domains_path=str(opath), osm_feed_refresh_hours=336)
    runner = build_runner(cfg)
    assert runner._harvester is not None      # osm_feed alone must build the harvester
    assert runner._osm_feed is not None


from crawler.discovery.aggregator_feed import AggregatorDomainFeed


def test_build_runner_wires_aggregator_feed(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False, osm_feed_enabled=False,
        aggregator_feed_enabled=True, aggregator_domains_path=str(tmp_path / "agg.json"))
    runner = build_runner(cfg)
    assert isinstance(runner._aggregator_feed, AggregatorDomainFeed)
    assert runner._harvester is not None and runner._harvester._aggregator_store is not None


def test_build_runner_aggregator_feed_disabled(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False, osm_feed_enabled=False,
        aggregator_feed_enabled=False)
    runner = build_runner(cfg)
    assert runner._aggregator_feed is None


def test_build_runner_aggregator_only_still_builds_harvester(tmp_path):
    # aggregator feed enabled, everything else off → harvester must still be built
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False, osm_feed_enabled=False,
        domain_rating_enabled=False, aggregator_feed_enabled=True,
        aggregator_domains_path=str(tmp_path / "agg.json"))
    runner = build_runner(cfg)
    assert runner._harvester is not None
    assert runner._harvester._aggregator_store is not None


def test_build_runner_grid_has_cities(tmp_path):
    # isolate the city axis: query_lexicon off so the always-on service seed
    # doesn't add to the base+geo count.
    cfg = _base_cfg(tmp_path, active_discovery=True, search_providers=["duckduckgo"],
                    grid_cities_enabled=True, query_lexicon_enabled=False)
    runner = build_runner(cfg)
    assert len(runner._search_pass._grid) == 1701


def test_build_runner_grid_cities_disabled(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=True, search_providers=["duckduckgo"],
                    grid_cities_enabled=False, query_lexicon_enabled=False)
    runner = build_runner(cfg)
    assert len(runner._search_pass._grid) == 351


def test_build_runner_grid_includes_seed_and_learned_services(tmp_path, monkeypatch):
    # With the feature enabled: curated SEED_SERVICES are always in the grid,
    # and miner-learned terms add on top of them — both × 6 service phrases.
    import crawler.discovery.query_lexicon as ql
    from crawler.discovery.query_grid import SEED_SERVICES
    monkeypatch.setattr(ql, "reload_learned", lambda *_a, **_k: None)
    monkeypatch.setattr(ql, "_cats", ())
    monkeypatch.setattr(ql, "_mined", ("стоматологія", "автосервіс"))
    cfg = _base_cfg(tmp_path, active_discovery=True, search_providers=["duckduckgo"],
                    grid_cities_enabled=True, query_lexicon_enabled=True)
    runner = build_runner(cfg)
    assert len(runner._search_pass._grid) == 1701 + (len(SEED_SERVICES) + 2) * 6


def test_build_runner_query_lexicon_disabled_is_1701(tmp_path, monkeypatch):
    import crawler.discovery.query_lexicon as ql
    monkeypatch.setattr(ql, "reload_learned", lambda *_a, **_k: None)
    monkeypatch.setattr(ql, "_mined", ("стоматологія",))
    cfg = _base_cfg(tmp_path, active_discovery=True, search_providers=["duckduckgo"],
                    grid_cities_enabled=True, query_lexicon_enabled=False)
    runner = build_runner(cfg)
    assert len(runner._search_pass._grid) == 1701           # seed + learned suppressed by flag


def test_reject_ingestor_built_and_reuses_registry(tmp_path):
    cfg = _harvest_config(tmp_path, brand_feed_enabled=False, sitemap_depth_enabled=False,
                          domain_rating_enabled=True,
                          domain_registry_path=str(tmp_path / "reg.json"),
                          rejection_feedback_enabled=True)
    runner = build_runner(cfg)
    assert runner._reject_ingestor is not None
    assert runner._reject_ingestor._reg is runner._domain_registry   # same registry object


def test_reject_ingestor_absent_when_feedback_disabled(tmp_path):
    cfg = _harvest_config(tmp_path, brand_feed_enabled=False, sitemap_depth_enabled=False,
                          domain_rating_enabled=True,
                          domain_registry_path=str(tmp_path / "reg.json"),
                          rejection_feedback_enabled=False)
    assert build_runner(cfg)._reject_ingestor is None


def test_reject_ingestor_absent_when_rating_disabled(tmp_path):
    cfg = _harvest_config(tmp_path, brand_feed_enabled=False, sitemap_depth_enabled=False,
                          domain_rating_enabled=False, rejection_feedback_enabled=True)
    assert build_runner(cfg)._reject_ingestor is None
