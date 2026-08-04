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


def test_load_blocked_wrong_shaped_scalar_does_not_raise(tmp_path):
    p = tmp_path / "q_stop.json"
    p.write_text("42", encoding="utf-8")
    assert qs.load_blocked(str(p)) == {}

    p.write_text("null", encoding="utf-8")
    assert qs.load_blocked(str(p)) == {}


def test_reject_with_non_dict_candidates_does_not_raise(tmp_path):
    cand = tmp_path / "q_cand.json"
    cand.write_text(json.dumps(["кава"]), encoding="utf-8")
    stop = str(tmp_path / "q_stop.json")

    qs.reject("кава", str(cand), stop)

    # term is still recorded, with z=0.0 since no matching candidate dict was found
    assert qs.load_blocked(stop) == {"кава": 0.0}


def test_cli_reject_and_unstop(tmp_path):
    cand = _cands(tmp_path)
    stop = str(tmp_path / "q_stop.json")

    qs._main(["reject", "кава", "--candidates", cand, "--stoplist", stop])
    assert "кава" in qs.load_blocked(stop)

    qs._main(["unstop", "кава", "--stoplist", stop])
    assert "кава" not in qs.load_blocked(stop)


def test_reject_twice_is_idempotent_and_keeps_original_z(tmp_path):
    cand = _cands(tmp_path)
    stop = str(tmp_path / "q_stop.json")

    qs.reject("кава", cand, stop)
    assert qs.load_blocked(stop) == {"кава": 3.0}

    # second reject: candidates file no longer has "кава" (z would default to 0.0
    # if overwritten), so idempotency must preserve the original z=3.0 and not duplicate
    qs.reject("кава", cand, stop)

    raw = json.loads(open(stop, encoding="utf-8").read())
    matches = [e for e in raw if e.get("term") == "кава"]
    assert len(matches) == 1
    assert matches[0]["z"] == 3.0
    assert qs.load_blocked(stop) == {"кава": 3.0}
