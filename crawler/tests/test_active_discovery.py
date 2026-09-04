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


class _ServedProvider:
    """Provider exposing a per-keyword last_served, like SearchCache/SearxngProvider."""
    def __init__(self, served_map):
        self.served_map = served_map
        self.last_served = True

    def __call__(self, kw, page=1):
        self.last_served = self.served_map.get(kw, True)
        return []


def test_last_served_phrases_records_only_served():
    prov = _ServedProvider({"a": True, "b": False, "c": True})
    ad = ActiveDiscovery(budget=0, search_provider=prov)
    ad.run(["a", "b", "c"], set())
    assert ad.last_served_phrases == {"a", "c"}      # censored 'b' excluded


def test_last_served_phrases_unknown_provider_all_served():
    def provider(kw, page=1):                         # no last_served attribute
        return []
    ad = ActiveDiscovery(budget=0, search_provider=provider)
    ad.run(["a", "b"], set())
    assert ad.last_served_phrases == {"a", "b"}       # fail-safe: unknown → served


def test_last_served_phrases_excludes_raising_keyword():
    def provider(kw, page=1):
        if kw == "b":
            raise RuntimeError("boom")
        return []
    provider.last_served = True
    ad = ActiveDiscovery(budget=0, search_provider=provider)
    ad.run(["a", "b"], set())
    assert ad.last_served_phrases == {"a"}            # raised 'b' is censored


def test_zero_budget_is_unlimited():
    from crawler.models import SourceCandidate
    calls = []
    def provider(keyword, page=1):
        calls.append(keyword)
        return [SourceCandidate(name=keyword, type="telegram", url_or_handle=f"t.me/{keyword}")]
    ad = ActiveDiscovery(budget=0, search_provider=provider)
    ad.run(["a", "b", "c"], set())
    assert calls == ["a", "b", "c"]     # 0 == unlimited, all keywords processed
