from crawler import __main__ as m


def test_loop_command_dispatches_run_loop(monkeypatch):
    called = {}

    class _FakeRunner:
        def search_available(self):
            return True

    fake_runner = _FakeRunner()
    monkeypatch.setattr(m, "build_runner", lambda cfg: fake_runner)
    monkeypatch.setattr(m, "run_loop", lambda *a, **k: called.setdefault("ran", (a, k)))
    rc = m.main(["loop"])
    assert rc == 0
    assert "ran" in called
    assert called["ran"][1]["search_available"] == fake_runner.search_available


def test_run_command_still_one_shot(monkeypatch):
    seen = {}

    class _R:
        def run(self):
            seen["run"] = True
            return {"offers": 0}

    monkeypatch.setattr(m, "build_runner", lambda cfg: _R())
    assert m.main(["run"]) == 0
    assert seen.get("run") is True
