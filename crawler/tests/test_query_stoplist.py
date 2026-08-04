import json

from crawler.learn import query_stoplist as qs


def _cands(tmp_path):
    p = tmp_path / "q_cand.json"
    p.write_text(json.dumps([{"term": "кава", "z": 3.0, "support": 4}]), encoding="utf-8")
    return str(p)


def test_reject_writes_term_and_z_and_drops_candidate(tmp_path):
    cand = _cands(tmp_path)
    stop = str(tmp_path / "q_stop.json")
    qs.reject("кава", cand, stop)
    assert qs.load_blocked(stop) == {"кава": 3.0}
    assert json.loads(open(cand, encoding="utf-8").read()) == []   # removed from queue


def test_is_suppressed_until_z_exceeds_factor():
    blocked = {"кава": 3.0}
    assert qs.is_suppressed("кава", 5.0, blocked, factor=2.0) is True    # 5 <= 3*2
    assert qs.is_suppressed("кава", 6.5, blocked, factor=2.0) is False   # 6.5 > 6 -> resurface
    assert qs.is_suppressed("чай", 1.0, blocked, factor=2.0) is False    # not blocked


def test_unstop_removes_term(tmp_path):
    stop = str(tmp_path / "q_stop.json")
    qs.reject("кава", _cands(tmp_path), stop)
    qs.unstop("кава", stop)
    assert qs.load_blocked(stop) == {}
