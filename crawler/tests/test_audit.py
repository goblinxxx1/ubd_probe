import json
from crawler.learn.audit import write_candidates, approve, reject, load_stoplist
from crawler.learn.miner import TermScore


def _ts(term):
    return TermScore(term=term, z=3.0, pass_count=5, fail_count=0,
                     domains={"a.ua", "b.ua", "c.ua"})


def test_approve_moves_term_to_learned(tmp_path):
    cand = str(tmp_path / "candidates.json")
    learned = str(tmp_path / "learned.json")
    write_candidates(cand, [_ts("уцінка")])
    approve("уцінка", cand, learned)
    terms = [e["term"] for e in json.load(open(learned, encoding="utf-8"))]
    assert "уцінка" in terms
    assert all(e["term"] != "уцінка" for e in json.load(open(cand, encoding="utf-8")))


def test_reject_adds_to_stoplist(tmp_path):
    cand = str(tmp_path / "candidates.json")
    stop = str(tmp_path / "stop.json")
    write_candidates(cand, [_ts("розклад")])
    reject("розклад", cand, stop)
    assert "розклад" in load_stoplist(stop)
