from crawler.discovery.providers import SearchCache
from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _cand(url="https://a.example/x"):
    return [SourceCandidate(name="S", type="website", url_or_handle=url)]


def _cache(tmp_path, clock, inner, ttl=100.0):
    st = SearchState(str(tmp_path / "state.json"), clock=clock)
    return SearchCache(inner, st, ttl_seconds=ttl), st


def test_cache_miss_calls_inner_and_stores(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, Clock(), inner)
    out = cache("kw")
    assert [c.url_or_handle for c in out] == ["https://a.example/x"]
    assert calls == ["kw"]


def test_cache_hit_skips_inner(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, Clock(), inner)
    cache("kw")
    cache("kw")                       # second call within TTL
    assert calls == ["kw"]            # inner called only once


def test_cache_expiry_requeries(tmp_path):
    calls = []
    clk = Clock(1000.0)

    def inner(kw):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, clk, inner, ttl=100.0)
    cache("kw")
    clk.t = 1101.0
    cache("kw")
    assert calls == ["kw", "kw"]


def test_empty_result_is_cached(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        return []

    cache, _ = _cache(tmp_path, Clock(), inner)
    assert cache("kw") == []
    assert cache("kw") == []
    assert calls == ["kw"]           # empty cached, inner not called again


def test_backoff_tripped_during_call_not_cached(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        st.set_global_backoff(3600.0)   # inner trips global backoff, returns degraded []
        return []

    cache, st = _cache(tmp_path, Clock(), lambda kw: inner(kw))
    assert cache("kw") == []
    # not cached: next non-backoff call would re-query. Simulate backoff cleared:
    st.set_global_backoff(-3600.0)      # move next_allowed_at into the past
    cache("kw")
    assert calls == ["kw", "kw"]


def test_in_backoff_returns_empty_without_inner(tmp_path):
    calls = []
    cache, st = _cache(tmp_path, Clock(), lambda kw: calls.append(kw) or [])
    st.set_global_backoff(3600.0)
    assert cache("kw") == []
    assert calls == []
