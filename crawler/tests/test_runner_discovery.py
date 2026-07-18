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


class FakeDiscovery:
    def __init__(self, cands): self._cands = cands; self.called_with = None
    def run(self, keywords, known):
        self.called_with = (keywords, set(known))
        return self._cands


class FakeHarvester:
    def __init__(self): self.calls = []
    def harvest(self, candidates, cats, known, summary):
        self.calls.append(list(candidates))
        summary["offers"] += len(candidates)


def _runner(api, discovery, harvester):
    return Runner(api, {}, extractor=None, rate_limiter=None, discovery=discovery,
                  keywords=["знижки ветеранам"], harvester=harvester)


def test_runner_delegates_active_candidates_to_harvester():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website", url_or_handle="https://cafe.example")
    h = FakeHarvester()
    summary = _runner(api, FakeDiscovery([cand]), h).run()
    assert h.calls == [[cand]]
    assert summary["offers"] == 1
    assert api.suggested == []          # no blind per-result suggestions anymore


def test_runner_without_harvester_emits_nothing():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website", url_or_handle="https://cafe.example")
    _runner(api, FakeDiscovery([cand]), None).run()
    assert api.offers == [] and api.suggested == []


def test_runner_no_discovery_is_quiet():
    api = FakeApi()
    _runner(api, None, None).run()
    assert api.offers == [] and api.suggested == []
