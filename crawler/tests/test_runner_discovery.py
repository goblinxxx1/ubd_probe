from crawler.runner import Runner
from crawler.models import SourceCandidate


class FakeApi:
    def __init__(self):
        self.offers = []
        self.suggested = []
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True): return []
    def submit_offer(self, p): self.offers.append(p); return {}
    def submit_suggestion(self, p): self.suggested.append(p); return {}


class FakeSearchPass:
    def __init__(self, cands, drain_cands=None, site_discovery=None):
        self._cands = cands
        self._drain = drain_cands or []
        self._site_discovery = site_discovery
        self.called_with = None
        self.ran = False
    def run(self, known):
        self.ran = True
        self.called_with = set(known)
        return self._cands
    def drain(self):
        return list(self._drain)
    def provider_for_site_query(self): return self._site_discovery


class FakeDiscovery:
    def __init__(self): self.ran = False
    def run(self, queries, known): self.ran = True; return []


class FakeSitePlanner:
    def next_batch(self, reg, budget, cursor): return (["site:x знижка"], cursor + 1)


class FakeSiteState:
    def __init__(self): self.site_cursor = 0
    def set_site_cursor(self, v): self.site_cursor = v


class FakeRegistry:
    def top(self, n, known_hosts, cooldown): return ["x.example"]
    def prune(self, a, b): pass
    def save(self): pass


class FakeHarvester:
    def __init__(self): self.calls = []
    def harvest(self, candidates, cats, known, summary, known_hosts=None):
        self.calls.append(list(candidates))
        summary["offers"] += len(candidates)


def _runner(api, search_pass, harvester):
    return Runner(api, {}, extractor=None, rate_limiter=None, search_pass=search_pass,
                  harvester=harvester)


def _runner_with_site(api, search_pass, harvester, discovery):
    return Runner(api, {}, extractor=None, rate_limiter=None, search_pass=search_pass,
                  harvester=harvester, discovery=discovery,
                  site_planner=FakeSitePlanner(), site_state=FakeSiteState(),
                  domain_registry=FakeRegistry())


def test_runner_delegates_active_candidates_to_harvester():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website", url_or_handle="https://cafe.example")
    h = FakeHarvester()
    summary = _runner(api, FakeSearchPass([cand]), h).run()
    assert h.calls == [[cand]]
    assert summary["offers"] == 1
    assert api.suggested == []          # no blind per-result suggestions anymore


def test_runner_without_harvester_emits_nothing():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website", url_or_handle="https://cafe.example")
    _runner(api, FakeSearchPass([cand]), None).run()
    assert api.offers == [] and api.suggested == []


def test_runner_no_discovery_is_quiet():
    api = FakeApi()
    _runner(api, None, None).run()
    assert api.offers == [] and api.suggested == []


def test_run_active_backoff_drains_without_searching():
    api = FakeApi()
    searched = SourceCandidate(name="s", type="website", url_or_handle="https://s.example")
    drained = SourceCandidate(name="d", type="website", url_or_handle="https://d.example")
    sp = FakeSearchPass([searched], drain_cands=[drained])
    h = FakeHarvester()
    _runner(api, sp, h).run_active(ddg_allowed=False)
    assert sp.ran is False                       # DDG due-walk search NOT called
    assert h.calls == [[drained]]                # only the drained candidate harvested


def test_run_active_ddg_allowed_runs_full_search():
    api = FakeApi()
    searched = SourceCandidate(name="s", type="website", url_or_handle="https://s.example")
    sp = FakeSearchPass([searched])
    h = FakeHarvester()
    _runner(api, sp, h).run_active(ddg_allowed=True)
    assert sp.ran is True
    assert h.calls == [[searched]]


def test_run_active_backoff_skips_site_queries():
    disc = FakeDiscovery()
    _runner_with_site(FakeApi(), FakeSearchPass([], drain_cands=[]),
                      FakeHarvester(), disc).run_active(ddg_allowed=False)
    assert disc.ran is False                      # site: DDG queries skipped under backoff


def test_run_active_ddg_allowed_runs_site_queries():
    disc = FakeDiscovery()
    # site: leg now takes its discovery from the healthy search_pass provider, not the
    # static self._discovery — so the fake search_pass must report `disc` as that provider.
    _runner_with_site(FakeApi(), FakeSearchPass([], drain_cands=[], site_discovery=disc),
                      FakeHarvester(), disc).run_active(ddg_allowed=True)
    assert disc.ran is True
