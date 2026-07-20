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

    def text(self, query, max_results=7, backend=None):
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
        def text(self, query, max_results=7, backend=None):
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


def test_all_cooled_sets_global_backoff_and_returns_empty(tmp_path):
    class Boom:
        def text(self, query, max_results=7, backend=None):
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
