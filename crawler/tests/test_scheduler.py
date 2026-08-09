from crawler.scheduler import step, run_loop, MIN_ACTIVE_DELAY


class _Runner:
    def __init__(self):
        self.calls = []

    def run_active(self):
        self.calls.append("active")

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
    assert r.calls == ["active"]


def test_active_delay_floor():
    r = _Runner()
    assert step(r, _State(False), _Passive(), **_kw(active_delay=0)) == MIN_ACTIVE_DELAY


def test_backed_off_passive_due_runs_passive_sleeps_to_T():
    r, p = _Runner(), _Passive(due=True)
    assert step(r, _State(True, secs=500), p, **_kw()) == 500
    assert r.calls == ["passive"] and p.marked == 1


def test_backed_off_passive_not_due_sleeps_capped_no_pass():
    r = _Runner()
    assert step(r, _State(True, secs=9999), _Passive(due=False), **_kw()) == 1800
    assert r.calls == []


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
    assert r.calls == ["passive", "active"] and slept == [100, 60]


def test_run_loop_survives_pass_error():
    class Boom:
        def run_active(self):
            raise RuntimeError("boom")

        def run_passive(self):
            pass

    slept = []
    run_loop(Boom(), lambda: _State(False), _Passive(),
             sleep=slept.append, iterations=1, **_kw())
    assert slept == [60]   # error swallowed, slept active_delay
