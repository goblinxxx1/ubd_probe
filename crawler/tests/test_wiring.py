from crawler.config import Config
from crawler.extract.base import CategoryIndex
from crawler.models import RawItem
from crawler.wiring import build_runner


def test_build_runner_wires_all_platforms():
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False,
    )
    runner = build_runner(cfg)
    assert set(runner._fetchers.keys()) == {"website", "telegram", "instagram", "facebook"}
    # extractor is the heuristic one (returns None on non-offer text)
    assert runner._extractor.extract(RawItem(1, "website", "k", ""), "P",
                                     CategoryIndex([], [])) is None


from crawler.discovery.query_grid import QueryGrid
from crawler.discovery.search_state import SearchState


def test_build_runner_rotates_query_grid_and_unions_pins(tmp_path):
    state_path = str(tmp_path / "state.json")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=True, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        search_providers=[],                 # provider None -> no network at build
        search_keywords=["мій пін"],
        search_state_path=state_path,
        search_queries_per_pass=3,
        brand_feed_enabled=False,
    )
    runner = build_runner(cfg)

    expected_batch, expected_cursor = QueryGrid().next_batch(3, 0)
    assert runner._keywords == expected_batch + ["мій пін"]
    assert SearchState.load(state_path).grid_cursor == expected_cursor


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

    class _Discovery:
        def run(self, keywords, known):
            return [SourceCandidate(name="ddg", type="website",
                                    url_or_handle="https://ddg.example")]

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
                    discovery=_Discovery(), keywords=["kw"], harvester=harv,
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

    class _EmptyDiscovery:
        def run(self, keywords, known):
            return []

    class _Harvester:
        def __init__(self):
            self.called = False

        def harvest(self, candidates, cats, known, summary):
            self.called = True

    harv = _Harvester()
    runner = Runner(_Api(), {}, extractor=None, rate_limiter=None,
                    discovery=_EmptyDiscovery(), keywords=["kw"], harvester=harv,
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
                 sitemap_depth_enabled=False)
    r = build_runner(cfg)
    assert r._corpus is None


def test_domain_rating_off_is_byte_equivalent(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False,
        domain_rating_enabled=False,
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
        domain_rating_enabled=True,
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
        domain_rating_enabled=True,
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
        blocked_hosts_fetch_enabled=True,
    )
    w.build_runner(cfg)   # must not raise
