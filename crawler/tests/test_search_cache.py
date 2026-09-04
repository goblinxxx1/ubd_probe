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

    def inner(kw, page=1):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, Clock(), inner)
    out = cache("kw")
    assert [c.url_or_handle for c in out] == ["https://a.example/x"]
    assert calls == ["kw"]


def test_cache_hit_skips_inner(tmp_path):
    calls = []

    def inner(kw, page=1):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, Clock(), inner)
    cache("kw")
    cache("kw")                       # second call within TTL
    assert calls == ["kw"]            # inner called only once


def test_cache_expiry_requeries(tmp_path):
    calls = []
    clk = Clock(1000.0)

    def inner(kw, page=1):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, clk, inner, ttl=100.0)
    cache("kw")
    clk.t = 1101.0
    cache("kw")
    assert calls == ["kw", "kw"]


def test_empty_result_is_cached(tmp_path):
    calls = []

    def inner(kw, page=1):
        calls.append(kw)
        return []

    cache, _ = _cache(tmp_path, Clock(), inner)
    assert cache("kw") == []
    assert cache("kw") == []
    assert calls == ["kw"]           # empty cached, inner not called again


def test_backoff_tripped_during_call_not_cached(tmp_path):
    calls = []

    def inner(kw, page=1):
        calls.append(kw)
        st.set_global_backoff(3600.0)   # inner trips global backoff, returns degraded []
        return []

    cache, st = _cache(tmp_path, Clock(), lambda kw, page=1: inner(kw, page))
    assert cache("kw") == []
    # not cached: next non-backoff call would re-query. Simulate backoff cleared:
    st.set_global_backoff(-3600.0)      # move next_allowed_at into the past
    cache("kw")
    assert calls == ["kw", "kw"]


def test_in_backoff_returns_empty_without_inner(tmp_path):
    calls = []
    cache, st = _cache(tmp_path, Clock(), lambda kw, page=1: calls.append(kw) or [])
    st.set_global_backoff(3600.0)
    assert cache("kw") == []
    assert calls == []


class _Inner:
    """Inner provider that exposes a controllable per-call last_served, like the real ones."""
    def __init__(self, served, results=None):
        self.served = served
        self.results = results if results is not None else []
        self.last_served = None
        self.calls = 0

    def __call__(self, kw, page=1):
        self.calls += 1
        self.last_served = self.served
        return list(self.results)


def test_cache_propagates_last_served_from_inner(tmp_path):
    inner = _Inner(served=False)
    cache, _ = _cache(tmp_path, Clock(), inner)
    cache("kw")
    assert cache.last_served is False        # censored inner → censored cache


def test_cache_hit_is_served(tmp_path):
    inner = _Inner(served=True, results=_cand())
    cache, _ = _cache(tmp_path, Clock(), inner)
    cache("kw")                              # miss → stores
    inner.served = False                     # channel goes down afterwards
    cache("kw")                              # HIT → inner not consulted
    assert inner.calls == 1
    assert cache.last_served is True         # cached data IS a served observation


def test_backoff_shortcircuit_is_censored(tmp_path):
    inner = _Inner(served=True, results=_cand())
    cache, st = _cache(tmp_path, Clock(), inner)
    st.set_global_backoff(3600.0)
    assert cache("kw") == []
    assert inner.calls == 0
    assert cache.last_served is False        # nothing served under backoff


def test_degraded_empty_not_cached(tmp_path):
    calls = []

    def inner(kw, page=1):
        calls.append(kw)
        st.mark_degraded()          # provider signals a degraded pass (all attempted backends failed)
        return []

    cache, st = _cache(tmp_path, Clock(), inner)
    assert cache("kw") == []
    assert cache("kw") == []
    assert calls == ["kw", "kw"]    # degraded empty NOT cached -> inner re-queried
