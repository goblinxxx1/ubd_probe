from crawler.schedule import PassiveSchedule


def test_due_when_no_state_file(tmp_path):
    s = PassiveSchedule(str(tmp_path / "p.json"), 100, now=lambda: 1000.0)
    assert s.due() is True


def test_not_due_within_interval_then_due_after(tmp_path):
    t = {"v": 1000.0}
    s = PassiveSchedule(str(tmp_path / "p.json"), 100, now=lambda: t["v"])
    s.mark()
    t["v"] = 1050.0
    assert s.due() is False
    t["v"] = 1101.0
    assert s.due() is True


def test_mark_persists_across_instances(tmp_path):
    p = str(tmp_path / "p.json")
    PassiveSchedule(p, 100, now=lambda: 500.0).mark()
    assert PassiveSchedule(p, 100, now=lambda: 550.0).due() is False
    assert PassiveSchedule(p, 100, now=lambda: 601.0).due() is True


def test_corrupt_file_is_due(tmp_path):
    p = tmp_path / "p.json"
    p.write_text("{bad", encoding="utf-8")
    assert PassiveSchedule(str(p), 100, now=lambda: 1.0).due() is True
