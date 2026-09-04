from ddgs.exceptions import DDGSException, RatelimitException

from crawler.discovery.providers import RotatingDdgProvider
from crawler.discovery.search_state import SearchState

POOL = ["google", "startpage", "duckduckgo", "yahoo", "brave"]


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class RecordingDDGS:
    """Returns fixed results and records which backend was requested."""
    def __init__(self, results, log):
        self._results = results
        self._log = log

    def text(self, query, max_results=7, backend=None, page=1):
        self._log.append(backend)
        return self._results


def _provider(tmp_path, clock, factory, **over):
    st = SearchState(str(tmp_path / "state.json"), clock=clock)
    kw = dict(pool=POOL, state=st, results_per_keyword=7, min_delay=1.0, jitter=0.0,
              cooldown_base=300.0, cooldown_cap=21600.0, global_backoff_seconds=3600.0,
              ddgs_factory=factory, sleep=lambda _s: None, rand=lambda: 0.0)
    kw.update(over)
    return RotatingDdgProvider(**kw), st


def test_rotation_uses_one_backend_per_query_round_robin(tmp_path):
    log = []
    factory = lambda: RecordingDDGS([{"title": "S", "href": "https://a.example/x"}], log)
    p, _ = _provider(tmp_path, Clock(), factory)
    for _ in range(6):
        p("kw")
    assert log == ["google", "startpage", "duckduckgo", "yahoo", "brave", "google"]


def test_classifies_results_with_backend_note(tmp_path):
    log = []
    factory = lambda: RecordingDDGS([{"title": "Shop", "href": "https://a.example/x"}], log)
    p, _ = _provider(tmp_path, Clock(), factory)
    cands = p("знижки")
    assert cands[0].type == "website"
    assert cands[0].url_or_handle == "https://a.example/x"
    assert cands[0].discovery_note == "ddg:google: знижки"


def test_blocked_backend_falls_through_to_next(tmp_path):
    log = []

    class Flaky:
        def text(self, query, max_results=7, backend=None, page=1):
            log.append(backend)
            if backend == "google":
                raise RuntimeError("429")
            return [{"title": "S", "href": "https://a.example/x"}]

    p, st = _provider(tmp_path, Clock(), lambda: Flaky())
    cands = p("kw")
    assert log == ["google", "startpage"]          # google failed, startpage served
    assert cands[0].url_or_handle == "https://a.example/x"
    assert st.is_healthy("google") is False         # google cooled
    assert st.is_healthy("startpage") is True


def test_no_results_does_not_cool_backend(tmp_path):
    """ddgs raises DDGSException('No results found.') when a backend responds fine but
    the query genuinely has zero hits (mojeek's tiny index vs a UA query). That is NOT a
    block: the backend stays healthy and the query falls through to the next backend."""
    log = []

    class EmptyThenHit:
        def text(self, query, max_results=7, backend=None, page=1):
            log.append(backend)
            if backend == "google":
                raise DDGSException("No results found.")
            return [{"title": "S", "href": "https://a.example/x"}]

    p, st = _provider(tmp_path, Clock(), lambda: EmptyThenHit())
    cands = p("kw")
    assert log == ["google", "startpage"]           # google empty → fell through
    assert cands[0].url_or_handle == "https://a.example/x"
    assert st.is_healthy("google") is True          # NOT cooled — it answered, just empty
    assert st.degraded_last_call() is False          # a served result is not degraded


def test_all_empty_leaves_backends_healthy(tmp_path):
    """Every attempted backend legitimately empty → query yields [] and is flagged degraded
    (so the empty is not cached), but no healthy backend is cooled or quarantined."""
    class AllEmpty:
        def text(self, query, max_results=7, backend=None, page=1):
            raise DDGSException("No results found.")

    p, st = _provider(tmp_path, Clock(), lambda: AllEmpty(),
                      quarantine_threshold=2, quarantine_hours=24.0, reprobe_hours=6.0)
    for _ in range(8):
        assert p("kw") == []
    assert st.is_healthy("google") is True
    assert st.is_quarantined("google") is False
    assert st.in_global_backoff() is False


def test_ratelimit_still_cools_backend(tmp_path):
    """A real throttle (RatelimitException) must still cool the backend as before."""
    class Limited:
        def text(self, query, max_results=7, backend=None, page=1):
            if backend == "google":
                raise RatelimitException("429 Too Many Requests")
            return [{"title": "S", "href": "https://a.example/x"}]

    p, st = _provider(tmp_path, Clock(), lambda: Limited())
    p("kw")
    assert st.is_healthy("google") is False          # real block → cooled


def test_all_cooled_sets_global_backoff_and_returns_empty(tmp_path):
    class Boom:
        def text(self, query, max_results=7, backend=None, page=1):
            raise RuntimeError("banned")

    # tiny pool so two attempts exhaust it
    p, st = _provider(tmp_path, Clock(), lambda: Boom(), pool=["google", "brave"])
    assert p("kw") == []
    assert st.is_healthy("google") is False
    assert st.is_healthy("brave") is False
    assert p("kw2") == []                            # already in global backoff
    assert st.in_global_backoff() is True


def test_global_backoff_short_circuits_without_network(tmp_path):
    log = []
    factory = lambda: RecordingDDGS([{"title": "S", "href": "https://a/x"}], log)
    p, st = _provider(tmp_path, Clock(), factory)
    st.set_global_backoff(3600.0)
    assert p("kw") == []
    assert log == []                                 # no ddgs call


def test_sleep_uses_min_delay_and_jitter(tmp_path):
    slept = []
    log = []
    factory = lambda: RecordingDDGS([], log)
    p, _ = _provider(tmp_path, Clock(), factory, min_delay=10.0, jitter=0.5,
                     sleep=lambda s: slept.append(s), rand=lambda: 1.0)
    p("kw")
    assert slept == [15.0]                            # 10 * (1 + 1.0*0.5)


def test_partial_failure_marks_degraded_without_global_backoff(tmp_path):
    log = []

    class AlwaysBad:
        def text(self, query, max_results=7, backend=None, page=1):
            log.append(backend)
            raise RuntimeError("429")

    # 3-backend pool: two attempts both fail, one backend stays untried & healthy
    p, st = _provider(tmp_path, Clock(), lambda: AlwaysBad(),
                      pool=["google", "startpage", "duckduckgo"])
    assert p("kw") == []
    assert len(log) == 2                       # only two attempts, not the whole pool
    assert st.degraded_last_call() is True     # signalled degraded
    assert st.in_global_backoff() is False     # but NOT global backoff -- a healthy backend remains
    assert st.is_healthy("duckduckgo") is True


def test_success_clears_degraded(tmp_path):
    log = []
    factory = lambda: RecordingDDGS([{"title": "S", "href": "https://a.example/x"}], log)
    p, st = _provider(tmp_path, Clock(), factory)
    st.mark_degraded()               # pretend a prior degraded pass
    p("kw")
    assert st.degraded_last_call() is False


class FailingDDGS:
    def text(self, query, max_results=7, backend=None, page=1):
        raise RuntimeError("boom")


def test_quarantined_backend_excluded_from_pool(tmp_path):
    clock = Clock()
    # cooldown_base=0 → a failed backend isn't cooled, so round-robin keeps hitting it and
    # google reaches the quarantine threshold. (With a real cooldown a dead backend is simply
    # skipped while cooled; quarantine is what stops it dragging all-cool once cooldown lapses.)
    p, st = _provider(tmp_path, clock, FailingDDGS, cooldown_base=0.0,
                      quarantine_threshold=2, quarantine_hours=24.0, reprobe_hours=6.0)
    for _ in range(8):                       # 2 backends per call → google fails >= 2
        p("kw")
    assert st.is_quarantined("google") is True


def test_adaptive_delay_scales_with_unhealthy(tmp_path):
    clock = Clock()
    p, st = _provider(tmp_path, clock, FailingDDGS, min_delay=10.0, jitter=0.0)
    # full health: multiplier 1.0
    assert p._adaptive_delay() == 10.0
    # quarantine 3 of 5 backends → 2 healthy → multiplier 5/2 = 2.5 → 25.0
    for name in ("google", "startpage", "duckduckgo"):
        st._data["backends"][name] = {"fails": 9, "cooldown_until": clock.t + 999,
                                      "quarantined_until": clock.t + 999, "next_reprobe_at": clock.t + 999}
    assert p._adaptive_delay() == 25.0


def test_all_cool_sets_dynamic_backoff_not_fixed_6h(tmp_path):
    clock = Clock()
    # cap cooldowns low so soonest_recovery is small; floor makes it 300
    p, st = _provider(tmp_path, clock, FailingDDGS, cooldown_base=10.0, cooldown_cap=50.0,
                      quarantine_threshold=99, backoff_floor=300.0)
    for _ in range(20):
        p("kw")           # exhaust all backends into cooldown
    secs = st.seconds_until_allowed()
    assert 0 < secs <= 300.0      # dynamic (<= floor), NOT 6h (21600)
