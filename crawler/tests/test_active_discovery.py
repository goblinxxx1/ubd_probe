from crawler.discovery.active import ActiveDiscovery
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate


def test_noop_provider_returns_nothing():
    ad = ActiveDiscovery(budget=5)
    assert ad.run(["знижки ветеранам"], set()) == []


def test_budget_caps_provider_calls():
    calls = []

    def provider(keyword, page=1):
        calls.append(keyword)
        return [SourceCandidate(name=keyword, type="telegram", url_or_handle=f"t.me/{keyword}")]

    ad = ActiveDiscovery(budget=2, search_provider=provider)
    out = ad.run(["a", "b", "c", "d"], set())
    assert len(calls) == 2          # budget enforced
    assert len(out) == 2


def test_filters_known():
    def provider(keyword, page=1):
        return [SourceCandidate(name="x", type="telegram", url_or_handle="t.me/known")]

    ad = ActiveDiscovery(budget=3, search_provider=provider)
    known = {normalize_ref("telegram", "t.me/known")}
    assert ad.run(["a"], known) == []


def test_pages_forwarded_per_keyword():
    seen = {}

    def provider(keyword, page=1):
        seen[keyword] = page
        return []

    ad = ActiveDiscovery(budget=0, search_provider=provider)
    ad.run(["a", "b"], set(), pages={"a": 2})
    assert seen == {"a": 2, "b": 1}          # per-keyword page; default 1


def test_zero_budget_is_unlimited():
    from crawler.models import SourceCandidate
    calls = []
    def provider(keyword, page=1):
        calls.append(keyword)
        return [SourceCandidate(name=keyword, type="telegram", url_or_handle=f"t.me/{keyword}")]
    ad = ActiveDiscovery(budget=0, search_provider=provider)
    ad.run(["a", "b", "c"], set())
    assert calls == ["a", "b", "c"]     # 0 == unlimited, all keywords processed
