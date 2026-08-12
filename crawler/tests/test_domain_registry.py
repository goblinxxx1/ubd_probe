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


def test_top_tie_break_by_host_on_equal_scores(tmp_path):
    r = _reg(tmp_path, offer_weight=1.0)
    r.record("b.ua", offers=5, errors=0)      # recorded first
    r.record("a.ua", offers=5, errors=0)      # equal score
    assert r.top(10, set()) == ["a.ua", "b.ua"]   # host asc, not insertion order


def test_seen_within_reflects_last_seen(tmp_path):
    t = {"v": 1000.0}
    r = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: t["v"])
    r.record("a.ua", offers=1, errors=0)   # last_seen = 1000
    t["v"] = 1000.0 + 50
    assert r.seen_within("a.ua", 100) is True
    assert r.seen_within("a.ua", 40) is False
    assert r.seen_within("never.ua", 100) is False


def test_top_excludes_recently_seen_when_cooldown_set(tmp_path):
    t = {"v": 1000.0}
    r = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: t["v"])
    r.record("hi.ua", offers=5, errors=0)    # highest score, seen at 1000
    t["v"] = 1000.0 + 10
    r.record("lo.ua", offers=1, errors=0)    # lower score, seen at 1010
    t["v"] = 1000.0 + 20
    assert r.top(10, set(), cooldown_seconds=100) == []
    assert r.top(10, set(), cooldown_seconds=0) == ["hi.ua", "lo.ua"]
    t["v"] = 1000.0 + 150
    assert r.top(10, set(), cooldown_seconds=100) == ["hi.ua", "lo.ua"]


def test_record_rejections_downranks_existing_host():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1000.0, reject_weight=1.0)
    reg.record("shop.ua", offers=3, errors=0)   # score 3.0
    reg.record_rejections("shop.ua", 2)          # -2.0 -> 1.0
    assert reg.score("shop.ua") == 1.0
    e = reg._data["domains"]["shop.ua"]
    assert e["rejects"] == 2
    assert e["offers"] == 3 and e["errors"] == 0 and e["passes"] == 1  # untouched


def test_record_rejections_clamps_at_zero():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1.0, reject_weight=1.0)
    reg.record("noisy.ua", offers=1, errors=0)   # 1.0
    reg.record_rejections("noisy.ua", 5)         # would be -4 -> clamp 0
    assert reg.score("noisy.ua") == 0.0


def test_record_rejections_skips_unknown_host():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1.0, reject_weight=1.0)
    reg.record_rejections("ghost.ua", 3)
    assert "ghost.ua" not in reg._data["domains"]
    assert reg.score("ghost.ua") == 0.0


def test_record_rejections_ignores_empty_host():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}}, clock=lambda: 1.0)
    reg.record_rejections("", 2)   # no crash, no entry
    assert reg._data["domains"] == {}


def test_record_rejections_does_not_move_last_seen():
    from crawler.discovery.domain_registry import DomainRegistry
    clk = [100.0]
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: clk[0], reject_weight=1.0)
    reg.record("a.ua", offers=2, errors=0)
    seen_before = reg._data["domains"]["a.ua"]["last_seen"]
    clk[0] = 900.0
    reg.record_rejections("a.ua", 1)
    assert reg._data["domains"]["a.ua"]["last_seen"] == seen_before   # cooldown/prune unaffected


# --- empty-pass skip: 0-offer pass -> skip the host's next N crawls ---
def test_empty_pass_arms_skip_counted_down_by_take_skip(tmp_path):
    r = _reg(tmp_path, empty_skip=3)
    r.record("empty.ua", offers=0, errors=0)      # empty pass -> skip next 3 crawls
    assert r.take_skip("empty.ua") is True         # skip 1
    assert r.take_skip("empty.ua") is True         # skip 2
    assert r.take_skip("empty.ua") is True         # skip 3
    assert r.take_skip("empty.ua") is False        # 4th crawl proceeds


def test_offers_clear_the_skip(tmp_path):
    r = _reg(tmp_path, empty_skip=3)
    r.record("x.ua", offers=0, errors=0)           # skip armed
    assert r.take_skip("x.ua") is True
    r.record("x.ua", offers=2, errors=0)           # found offers -> skip cleared
    assert r.take_skip("x.ua") is False


def test_take_skip_unknown_host_is_false(tmp_path):
    assert _reg(tmp_path).take_skip("never-seen.ua") is False


def test_default_empty_skip_is_five(tmp_path):
    r = _reg(tmp_path)                              # default empty_skip=5
    r.record("e.ua", offers=0, errors=0)
    assert sum(1 for _ in range(6) if r.take_skip("e.ua")) == 5   # 5 skips then allow
