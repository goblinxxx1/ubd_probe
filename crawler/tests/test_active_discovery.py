from crawler.discovery.active import ActiveDiscovery
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate


def test_noop_provider_returns_nothing():
    ad = ActiveDiscovery(budget=5)
    assert ad.run(["знижки ветеранам"], set()) == []


def test_budget_caps_provider_calls():
    calls = []

    def provider(keyword):
        calls.append(keyword)
        return [SourceCandidate(name=keyword, type="telegram", url_or_handle=f"t.me/{keyword}")]

    ad = ActiveDiscovery(budget=2, search_provider=provider)
    out = ad.run(["a", "b", "c", "d"], set())
    assert len(calls) == 2          # budget enforced
    assert len(out) == 2


def test_filters_known():
    def provider(keyword):
        return [SourceCandidate(name="x", type="telegram", url_or_handle="t.me/known")]

    ad = ActiveDiscovery(budget=3, search_provider=provider)
    known = {normalize_ref("telegram", "t.me/known")}
    assert ad.run(["a"], known) == []
