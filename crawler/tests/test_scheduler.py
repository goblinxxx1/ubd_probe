from crawler.scheduler import step, run_loop, MIN_ACTIVE_DELAY


class _Runner:
    def __init__(self):
        self.calls = []
        self.ddg_flags = []

    def run_active(self, ddg_allowed=True):
        self.calls.append("active")
        self.ddg_flags.append(ddg_allowed)

    def run_passive(self):
        self.calls.append("passive")


class _State:
    def __init__(self, backed_off, secs=0.0):
        self._b, self._s = backed_off, secs

    def in_global_backoff(self):
        return self._b

    def seconds_until_allowed(self):
        return self._s


class _Passive:
    def __init__(self, due=False, overdue=False):
        self._due, self._overdue, self.marked = due, overdue, 0

    def due(self):
        return self._due

    def overdue(self, f):
        return self._overdue

    def mark(self):
        self.marked += 1


def _kw(**over):
    base = dict(active_delay=60, backoff_max_sleep=1800, hard_factor=3)
    base.update(over)
    return base


def test_not_backed_off_runs_active():
    r = _Runner()
    assert step(r, _State(False), _Passive(), **_kw()) == 60
    assert r.calls == ["active"] and r.ddg_flags == [True]


def test_active_delay_floor():
    r = _Runner()
    assert step(r, _State(False), _Passive(), **_kw(active_delay=0)) == MIN_ACTIVE_DELAY


def test_backed_off_passive_due_runs_active_then_passive():
    r, p = _Runner(), _Passive(due=True)
    assert step(r, _State(True, secs=500), p, **_kw()) == 500
    assert r.calls == ["active", "passive"] and p.marked == 1
    assert r.ddg_flags == [False]              # active pass ran DDG-independent


def test_backed_off_passive_not_due_runs_ddg_independent_active():
    r = _Runner()
    assert step(r, _State(True, secs=9999), _Passive(due=False), **_kw()) == 1800
    assert r.calls == ["active"] and r.ddg_flags == [False]


def test_hard_overdue_runs_passive_in_active_window():
    r, p = _Runner(), _Passive(overdue=True)
    assert step(r, _State(False), p, **_kw()) == 60
    assert r.calls == ["passive"] and p.marked == 1


def test_state_none_runs_active():
    r = _Runner()
    step(r, None, _Passive(), **_kw())
    assert r.calls == ["active"]


def test_run_loop_bounded_iterations():
    r, slept = _Runner(), []
    states = iter([_State(True, 100), _State(False)])
    run_loop(r, lambda: next(states), _Passive(due=True),
             sleep=slept.append, iterations=2, **_kw())
    assert r.calls == ["active", "passive", "active"] and slept == [100, 60]


def test_run_loop_learn_fires_on_first_iteration():
    r, learned = _Runner(), []
    run_loop(r, lambda: _State(False), _Passive(), sleep=lambda _s: None,
             iterations=1, learn=lambda: learned.append(1),
             learn_interval_seconds=1000, now=lambda: 0.0, **_kw())
    assert learned == [1]


def test_run_loop_learn_gated_by_interval():
    r, learned = _Runner(), []
    times = iter([0.0, 10.0, 1000.0])   # one now() per iteration
    run_loop(r, lambda: _State(False), _Passive(), sleep=lambda _s: None,
             iterations=3, learn=lambda: learned.append(1),
             learn_interval_seconds=1000, now=lambda: next(times), **_kw())
    # t=0 fires (first); t=10 gated (10<1000 since last); t=1000 fires again
    assert len(learned) == 2


def test_run_loop_learn_never_kills_loop():
    r = _Runner()

    def boom():
        raise RuntimeError("learn blew up")

    run_loop(r, lambda: _State(False), _Passive(), sleep=lambda _s: None,
             iterations=1, learn=boom, learn_interval_seconds=1, now=lambda: 0.0, **_kw())
    assert r.calls == ["active"]   # the crawl pass still ran despite learn failure


def test_run_loop_no_learn_when_interval_zero():
    r, learned = _Runner(), []
    run_loop(r, lambda: _State(False), _Passive(), sleep=lambda _s: None,
             iterations=2, learn=lambda: learned.append(1),
             learn_interval_seconds=0, now=lambda: 0.0, **_kw())
    assert learned == []           # interval 0 disables the tick


def test_run_loop_survives_pass_error():
    class Boom:
        def run_active(self, ddg_allowed=True):
            raise RuntimeError("boom")

        def run_passive(self):
            pass

    slept = []
    run_loop(Boom(), lambda: _State(False), _Passive(),
             sleep=slept.append, iterations=1, **_kw())
    assert slept == [60]   # error swallowed, slept active_delay


def test_step_full_pass_when_any_provider_available():
    r = _Runner()
    # DDG in global backoff, but search_available() True (searxng alive)
    secs = step(r, _State(True, secs=120.0), None, active_delay=60, backoff_max_sleep=1800,
                hard_factor=3, search_available=lambda: True)
    assert r.ddg_flags == [True]        # full active pass, NOT degraded
    assert secs == 60                    # short sleep, not long backoff sleep


def test_step_degraded_when_no_provider_available():
    r = _Runner()
    secs = step(r, _State(True, secs=200.0), None, active_delay=60,
                backoff_max_sleep=1800, hard_factor=3, search_available=lambda: False)
    assert r.ddg_flags == [False]       # degraded (drain-only) pass
    assert secs == 200.0                 # sleep until soonest recovery


def test_step_backcompat_without_search_available():
    r = _Runner()
    # no search_available → falls back to state.in_global_backoff() (existing behavior)
    step(r, _State(True, secs=200.0), None, active_delay=60,
         backoff_max_sleep=1800, hard_factor=3)
    assert r.ddg_flags == [False]
