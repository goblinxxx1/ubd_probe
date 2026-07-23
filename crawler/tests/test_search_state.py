import json

from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _state(tmp_path, clock):
    return SearchState(str(tmp_path / "state.json"), clock=clock)


def test_fresh_backend_is_healthy(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.is_healthy("google") is True


def test_record_block_sets_exponential_cooldown(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    d1 = st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    assert d1 == 300.0                       # base * 2^0
    assert st.is_healthy("google") is False
    d2 = st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    assert d2 == 600.0                        # base * 2^1
    clk.t = 1000.0 + 600.0
    assert st.is_healthy("google") is True    # cooldown elapsed


def test_record_block_caps_cooldown(tmp_path):
    st = _state(tmp_path, Clock())
    d = None
    for _ in range(20):
        d = st.record_block("g", base=300.0, cap=1000.0, jitter=0.0, rand=lambda: 0.0)
    assert d == 1000.0


def test_record_success_resets(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    st.record_success("google")
    assert st.is_healthy("google") is True


def test_cursor_roundtrip(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.cursor == 0
    st.set_cursor(3)
    assert st.cursor == 3


def test_global_backoff(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    assert st.in_global_backoff() is False
    st.set_global_backoff(60.0)
    assert st.in_global_backoff() is True
    clk.t = 1061.0
    assert st.in_global_backoff() is False


def test_cache_put_get_within_ttl(tmp_path):
    st = _state(tmp_path, Clock())
    cands = [SourceCandidate(name="Shop", type="website", url_or_handle="https://a.example/x")]
    st.cache_put("Знижки УБД", cands)
    got = st.cache_get("  знижки убд  ", ttl_seconds=100.0)   # normalized key
    assert got is not None
    assert [(c.type, c.url_or_handle) for c in got] == [("website", "https://a.example/x")]
    assert got[0].discovery_note == "ddg-cache: знижки убд"


def test_cache_miss_after_ttl(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    st.cache_put("kw", [SourceCandidate(name="x", type="website", url_or_handle="https://a/x")])
    clk.t = 1101.0
    assert st.cache_get("kw", ttl_seconds=100.0) is None


def test_persistence_roundtrip_and_atomic_file(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_cursor(2)
    st.record_block("brave", base=10.0, cap=100.0, jitter=0.0, rand=lambda: 0.0)
    st.cache_put("kw", [SourceCandidate(name="x", type="website", url_or_handle="https://a/x")])
    reloaded = SearchState.load(path, clock=Clock())
    assert reloaded.cursor == 2
    assert reloaded.is_healthy("brave") is False
    assert reloaded.cache_get("kw", ttl_seconds=1e9) is not None
    with open(path, encoding="utf-8") as f:
        assert "cache" in json.load(f)


def test_load_missing_or_corrupt_starts_clean(tmp_path):
    missing = SearchState.load(str(tmp_path / "nope.json"), clock=Clock())
    assert missing.cursor == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    st = SearchState.load(str(bad), clock=Clock())
    assert st.cursor == 0
    assert st.is_healthy("x") is True


def test_load_missing_key_does_not_leak_into_fresh_instance(tmp_path):
    # A state file missing the "cache" key must not cause later instances to
    # share/inherit mutated state (regression: shared _EMPTY default).
    import json as _json
    path = tmp_path / "partial.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "next_allowed_at": 0.0,
                                 "backends": {}}), encoding="utf-8")
    st_a = SearchState.load(str(path), clock=Clock())
    st_a.cache_put("leaked", [])
    st_b = SearchState(str(tmp_path / "other.json"), clock=Clock())
    assert st_b.cache_get("leaked", ttl_seconds=1e9) is None


def test_load_non_object_json_starts_clean(tmp_path):
    bad = tmp_path / "arr.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    st = SearchState.load(str(bad), clock=Clock())
    assert st.cursor == 0
    assert st.is_healthy("x") is True


def test_degraded_flag_defaults_false_and_toggles(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.degraded_last_call() is False
    st.mark_degraded()
    assert st.degraded_last_call() is True
    st.clear_degraded()
    assert st.degraded_last_call() is False


def test_grid_cursor_defaults_zero(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.grid_cursor == 0


def test_set_grid_cursor_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_cursor(3)            # backend-rotation cursor
    st.set_grid_cursor(42)      # grid cursor — separate field
    reloaded = SearchState.load(path)
    assert reloaded.grid_cursor == 42
    assert reloaded.cursor == 3


def test_site_cursor_defaults_zero(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.site_cursor == 0


def test_set_site_cursor_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_grid_cursor(42)      # grid cursor — separate field
    st.set_site_cursor(5)       # site cursor — separate field
    reloaded = SearchState.load(path)
    assert reloaded.site_cursor == 5
    assert reloaded.grid_cursor == 42


def test_old_state_file_without_site_cursor_loads(tmp_path):
    import json as _json
    path = tmp_path / "partial.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "grid_cursor": 3,
                                 "next_allowed_at": 0.0, "backends": {}, "cache": {}}),
                    encoding="utf-8")
    st = SearchState.load(str(path), clock=Clock())
    assert st.site_cursor == 0          # missing key defaults cleanly
    assert st.grid_cursor == 3


def test_approved_cursor_defaults_zero_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    assert st.approved_cursor == 0
    st.set_approved_cursor(4)
    st.set_site_cursor(2)
    reloaded = SearchState.load(path)
    assert reloaded.approved_cursor == 4
    assert reloaded.site_cursor == 2      # independent cursors
