import json

from crawler.discovery.domain_registry import DomainRegistry


class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t


def _reg(tmp_path, clock=None, **kw):
    return DomainRegistry(str(tmp_path / "registry.json"),
                          clock=clock or Clock(), **kw)


def test_record_creates_entry_and_score(tmp_path):
    r = _reg(tmp_path, offer_weight=1.0)
    r.record("silpo.ua", offers=1, errors=0)
    assert r.score("silpo.ua") == 1.0


def test_score_decays_then_rewards(tmp_path):
    r = _reg(tmp_path, decay=0.9, offer_weight=1.0, error_weight=0.5)
    r.record("x.ua", offers=1, errors=0)          # 1.0
    r.record("x.ua", offers=0, errors=0)          # 1.0*0.9 = 0.9
    r.record("x.ua", offers=1, errors=2)          # 0.9*0.9 + 1 - 1.0 = 0.81
    assert abs(r.score("x.ua") - 0.81) < 1e-9


def test_score_never_negative(tmp_path):
    r = _reg(tmp_path, error_weight=0.5)
    r.record("bad.ua", offers=0, errors=10)
    assert r.score("bad.ua") == 0.0


def test_counters_and_timestamps(tmp_path):
    clock = Clock(2000.0)
    r = _reg(tmp_path, clock=clock)
    r.record("a.ua", offers=2, errors=1)
    clock.t = 2500.0
    r.record("a.ua", offers=0, errors=0)
    e = r._data["domains"]["a.ua"]
    assert e["offers"] == 2 and e["errors"] == 1
    assert e["passes"] == 2 and e["empty_passes"] == 1
    assert e["first_seen"] == 2000.0 and e["last_seen"] == 2500.0
    assert e["last_offer"] == 2000.0


def test_top_filters_threshold_and_known_and_sorts(tmp_path):
    r = _reg(tmp_path, promote_min_score=0.5)
    r.record("hi.ua", offers=3, errors=0)     # 3.0
    r.record("mid.ua", offers=1, errors=0)    # 1.0
    r.record("lo.ua", offers=0, errors=1)     # 0.0 (below 0.5)
    assert r.top(10, known_hosts=set()) == ["hi.ua", "mid.ua"]
    assert r.top(10, known_hosts={"hi.ua"}) == ["mid.ua"]
    assert r.top(1, known_hosts=set()) == ["hi.ua"]


def test_prune_needs_both_cold_and_old(tmp_path):
    clock = Clock(10_000.0)
    r = _reg(tmp_path, clock=clock)
    r.record("cold_old.ua", offers=0, errors=1)     # score 0.0, last_seen 10000
    r.record("cold_new.ua", offers=0, errors=1)
    r.record("warm_old.ua", offers=5, errors=0)     # score 5.0
    clock.t = 20_000.0
    r.record("cold_new.ua", offers=0, errors=1)     # last_seen bumped to 20000
    removed = r.prune(evict_min_score=0.1, evict_ttl_seconds=5000.0)
    assert removed == 1
    assert "cold_old.ua" not in r._data["domains"]
    assert "cold_new.ua" in r._data["domains"]   # too new
    assert "warm_old.ua" in r._data["domains"]   # too warm


def test_save_load_roundtrip(tmp_path):
    p = str(tmp_path / "registry.json")
    r = DomainRegistry(p, clock=Clock())
    r.record("s.ua", offers=1, errors=0)
    r.save()
    r2 = DomainRegistry.load(p, clock=Clock())
    assert r2.score("s.ua") == 1.0


def test_load_corrupt_starts_clean(tmp_path):
    p = str(tmp_path / "registry.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{ not json")
    r = DomainRegistry.load(p)
    assert r.top(10, set()) == []
