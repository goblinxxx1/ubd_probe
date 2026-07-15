from crawler.runner import Runner
from crawler.models import SourceCandidate


class FakeApi:
    def __init__(self):
        self.suggested = []
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True): return []
    def submit_suggestion(self, payload): self.suggested.append(payload); return {}


class FakeDiscovery:
    def __init__(self, cands): self._cands = cands; self.called_with = None
    def run(self, keywords, known):
        self.called_with = (keywords, set(known))
        return self._cands


def _runner(api, discovery):
    return Runner(api, {}, extractor=None, rate_limiter=None, discovery=discovery,
                  keywords=["знижки ветеранам"])


def test_discovery_submits_each_candidate_as_suggestion():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website",
                           url_or_handle="https://cafe.example", discovery_note="ddg: x")
    r = _runner(api, FakeDiscovery([cand]))
    summary = r.run()
    assert len(api.suggested) == 1
    assert api.suggested[0]["url_or_handle"] == "https://cafe.example"
    assert summary["suggestions"] == 1


def test_no_discovery_means_no_suggestions():
    api = FakeApi()
    r = _runner(api, None)
    r.run()
    assert api.suggested == []
