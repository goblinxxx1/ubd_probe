import json

from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _state(tmp_path, clock):
    return SearchState(str(tmp_path / "state.json"), clock=clock)


def test_fresh_backend_is_healthy(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.is_healthy("google") is True


def test_record_block_sets_exponential_cooldown(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    d1 = st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    assert d1 == 300.0                       # base * 2^0
    assert st.is_healthy("google") is False
    d2 = st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    assert d2 == 600.0                        # base * 2^1
    clk.t = 1000.0 + 600.0
    assert st.is_healthy("google") is True    # cooldown elapsed


def test_record_block_caps_cooldown(tmp_path):
    st = _state(tmp_path, Clock())
    d = None
    for _ in range(20):
        d = st.record_block("g", base=300.0, cap=1000.0, jitter=0.0, rand=lambda: 0.0)
    assert d == 1000.0


def test_record_success_resets(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    st.record_success("google")
    assert st.is_healthy("google") is True


def test_cursor_roundtrip(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.cursor == 0
    st.set_cursor(3)
    assert st.cursor == 3


def test_global_backoff(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    assert st.in_global_backoff() is False
    st.set_global_backoff(60.0)
    assert st.in_global_backoff() is True
    clk.t = 1061.0
    assert st.in_global_backoff() is False


def test_cache_put_get_within_ttl(tmp_path):
    st = _state(tmp_path, Clock())
    cands = [SourceCandidate(name="Shop", type="website", url_or_handle="https://a.example/x")]
    st.cache_put("Знижки УБД", cands)
    got = st.cache_get("  знижки убд  ", ttl_seconds=100.0)   # normalized key
    assert got is not None
    assert [(c.type, c.url_or_handle) for c in got] == [("website", "https://a.example/x")]
    assert got[0].discovery_note == "ddg-cache: знижки убд"


def test_cache_miss_after_ttl(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    st.cache_put("kw", [SourceCandidate(name="x", type="website", url_or_handle="https://a/x")])
    clk.t = 1101.0
    assert st.cache_get("kw", ttl_seconds=100.0) is None


def test_persistence_roundtrip_and_atomic_file(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_cursor(2)
    st.record_block("brave", base=10.0, cap=100.0, jitter=0.0, rand=lambda: 0.0)
    st.cache_put("kw", [SourceCandidate(name="x", type="website", url_or_handle="https://a/x")])
    reloaded = SearchState.load(path, clock=Clock())
    assert reloaded.cursor == 2
    assert reloaded.is_healthy("brave") is False
    assert reloaded.cache_get("kw", ttl_seconds=1e9) is not None
    with open(path, encoding="utf-8") as f:
        assert "cache" in json.load(f)


def test_seconds_until_allowed_future_then_past():
    clk = [1000.0]
    st = SearchState("x", data={"next_allowed_at": 1300.0}, clock=lambda: clk[0])
    assert st.seconds_until_allowed() == 300.0
    clk[0] = 1400.0
    assert st.seconds_until_allowed() == 0.0   # clamped, never negative


def test_load_missing_or_corrupt_starts_clean(tmp_path):
    missing = SearchState.load(str(tmp_path / "nope.json"), clock=Clock())
    assert missing.cursor == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    st = SearchState.load(str(bad), clock=Clock())
    assert st.cursor == 0
    assert st.is_healthy("x") is True


def test_load_missing_key_does_not_leak_into_fresh_instance(tmp_path):
    # A state file missing the "cache" key must not cause later instances to
    # share/inherit mutated state (regression: shared _EMPTY default).
    import json as _json
    path = tmp_path / "partial.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "next_allowed_at": 0.0,
                                 "backends": {}}), encoding="utf-8")
    st_a = SearchState.load(str(path), clock=Clock())
    st_a.cache_put("leaked", [])
    st_b = SearchState(str(tmp_path / "other.json"), clock=Clock())
    assert st_b.cache_get("leaked", ttl_seconds=1e9) is None


def test_load_non_object_json_starts_clean(tmp_path):
    bad = tmp_path / "arr.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    st = SearchState.load(str(bad), clock=Clock())
    assert st.cursor == 0
    assert st.is_healthy("x") is True


def test_degraded_flag_defaults_false_and_toggles(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.degraded_last_call() is False
    st.mark_degraded()
    assert st.degraded_last_call() is True
    st.clear_degraded()
    assert st.degraded_last_call() is False


def test_grid_cursor_defaults_zero(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.grid_cursor == 0


def test_set_grid_cursor_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_cursor(3)            # backend-rotation cursor
    st.set_grid_cursor(42)      # grid cursor — separate field
    reloaded = SearchState.load(path)
    assert reloaded.grid_cursor == 42
    assert reloaded.cursor == 3


def test_site_cursor_defaults_zero(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.site_cursor == 0


def test_set_site_cursor_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_grid_cursor(42)      # grid cursor — separate field
    st.set_site_cursor(5)       # site cursor — separate field
    reloaded = SearchState.load(path)
    assert reloaded.site_cursor == 5
    assert reloaded.grid_cursor == 42


def test_old_state_file_without_site_cursor_loads(tmp_path):
    import json as _json
    path = tmp_path / "partial.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "grid_cursor": 3,
                                 "next_allowed_at": 0.0, "backends": {}, "cache": {}}),
                    encoding="utf-8")
    st = SearchState.load(str(path), clock=Clock())
    assert st.site_cursor == 0          # missing key defaults cleanly
    assert st.grid_cursor == 3


def test_approved_cursor_defaults_zero_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    assert st.approved_cursor == 0
    st.set_approved_cursor(4)
    st.set_site_cursor(2)
    reloaded = SearchState.load(path)
    assert reloaded.approved_cursor == 4
    assert reloaded.site_cursor == 2      # independent cursors


def test_legacy_state_with_removed_cursors_loads(tmp_path):
    import json as _json
    path = tmp_path / "legacy.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "grid_cursor": 80,
                                 "block_cursor": 240, "cycle": 0, "searxng_cursor": 153,
                                 "next_allowed_at": 0.0, "backends": {}, "cache": {}}),
                    encoding="utf-8")
    st = SearchState.load(str(path), clock=Clock())
    assert st.grid_cursor == 80          # live rotation position preserved
    assert not hasattr(st, "block_cursor")   # removed property


def test_is_fresh_true_within_ttl_false_after(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    st.cache_put("Знижки УБД", [])
    assert st.is_fresh("  знижки убд  ", ttl_seconds=100.0) is True   # normalized, within ttl
    clk.t = 1101.0
    assert st.is_fresh("знижки убд", ttl_seconds=100.0) is False       # aged past ttl


def test_is_fresh_false_for_unseen_keyword(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.is_fresh("never searched", ttl_seconds=1e9) is False


def _cand(u):
    return SourceCandidate(name=u, type="website", url_or_handle=u)


def test_cache_put_marks_unharvested_and_unharvested_returns_it(tmp_path):
    from crawler.discovery.search_state import SearchState
    clk = [1000.0]
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: clk[0])
    st.cache_put("стоматологія убд", [_cand("https://a.ua"), _cand("https://b.ua")])
    out = st.unharvested(ttl_seconds=10_000)
    assert [k for k, _ in out] == ["стоматологія убд"]
    cands = out[0][1]
    assert [c.url_or_handle for c in cands] == ["https://a.ua", "https://b.ua"]
    assert all(c.origin_key == "стоматологія убд" for c in cands)


def test_mark_harvested_removes_from_unharvested(tmp_path):
    from crawler.discovery.search_state import SearchState
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put("шиномонтаж військовим", [_cand("https://a.ua")])
    st.mark_harvested(["шиномонтаж військовим"])
    assert st.unharvested(ttl_seconds=10_000) == []


def test_unharvested_skips_stale_by_ttl(tmp_path):
    from crawler.discovery.search_state import SearchState
    clk = [1000.0]
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: clk[0])
    st.cache_put("окуляри зсу", [_cand("https://a.ua")])
    clk[0] = 1000.0 + 20_000
    assert st.unharvested(ttl_seconds=10_000) == []


def test_legacy_entry_without_harvested_key_counts_as_done(tmp_path):
    import json
    from crawler.discovery.search_state import SearchState
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"version": 1, "cache": {
        "legacy phrase": {"ts": 1000.0, "candidates": [{"name": "x", "type": "website",
                                                          "url_or_handle": "https://x.ua"}]}}}),
                 encoding="utf-8")
    st = SearchState(str(p), clock=lambda: 1001.0)
    assert st.unharvested(ttl_seconds=10_000) == []


def test_unharvested_oldest_first(tmp_path):
    from crawler.discovery.search_state import SearchState
    clk = [1000.0]
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: clk[0])
    st.cache_put("phrase-old", [_cand("https://old.ua")])
    clk[0] = 2000.0
    st.cache_put("phrase-new", [_cand("https://new.ua")])
    assert [k for k, _ in st.unharvested(ttl_seconds=10_000)] == ["phrase-old", "phrase-new"]


def test_record_block_quarantines_at_threshold(tmp_path):
    clock = Clock(1000.0)
    st = SearchState(str(tmp_path / "s.json"), clock=clock)
    # 5 fails: not yet quarantined (threshold 6)
    for _ in range(5):
        st.record_block("google", 300.0, 21600.0, 0.0, lambda: 0.0,
                        quarantine_threshold=6, quarantine_seconds=24*3600, reprobe_seconds=6*3600)
    assert st.is_quarantined("google") is False
    # 6th fail: quarantined for 24h, first re-probe in 6h
    st.record_block("google", 300.0, 21600.0, 0.0, lambda: 0.0,
                    quarantine_threshold=6, quarantine_seconds=24*3600, reprobe_seconds=6*3600)
    assert st.is_quarantined("google") is True
    assert st.reprobe_due("google") is False
    clock.t += 6*3600            # 6h later → re-probe due
    assert st.reprobe_due("google") is True


def test_record_success_clears_quarantine(tmp_path):
    clock = Clock(1000.0)
    st = SearchState(str(tmp_path / "s.json"), clock=clock)
    for _ in range(6):
        st.record_block("google", 300.0, 21600.0, 0.0, lambda: 0.0,
                        quarantine_threshold=6, quarantine_seconds=24*3600, reprobe_seconds=6*3600)
    assert st.is_quarantined("google") is True
    st.record_success("google")
    assert st.is_quarantined("google") is False
    assert st.reprobe_due("google") is False


def test_cache_page_key_backcompat_and_isolation(tmp_path):
    st = _state(tmp_path, Clock())
    st.cache_put("стоматологія", [_cand("https://p1.ua")])            # page 1 (bare key)
    st.cache_put("стоматологія", [_cand("https://p2.ua")], page=2)     # page 2 (#p2 key)
    # page 1 and page 2 are isolated
    assert [c.url_or_handle for c in st.cache_get("стоматологія", 1e9)] == ["https://p1.ua"]
    assert [c.url_or_handle for c in st.cache_get("стоматологія", 1e9, page=2)] == ["https://p2.ua"]
    # page-1 stored under the bare key (byte-compatible with legacy entries)
    assert "стоматологія" in st._data["cache"]
    assert "стоматологія#p2" in st._data["cache"]


def test_is_fresh_is_page_scoped(tmp_path):
    st = _state(tmp_path, Clock())
    st.cache_put("готель", [_cand("https://a.ua")], page=1)
    assert st.is_fresh("готель", 1e9, page=1) is True
    assert st.is_fresh("готель", 1e9, page=2) is False        # page 2 not yet fetched


def test_current_page_defaults_one(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.current_page("барбершоп") == 1


def test_record_page_productive_advances(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_page_result("зуби", page=1, new_count=3, page_cap=3)
    assert st.current_page("зуби") == 2


def test_record_page_one_dry_probes_next(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_page_result("зуби", page=1, new_count=0, page_cap=3)   # first dry
    assert st.current_page("зуби") == 2                              # probe one more


def test_record_page_two_dry_stops_and_resets(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_page_result("зуби", page=1, new_count=0, page_cap=3)   # dry #1 -> page 2
    st.record_page_result("зуби", page=2, new_count=0, page_cap=3)   # dry #2 -> stop, reset
    assert st.current_page("зуби") == 1


def test_record_page_productive_resets_dry_counter(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_page_result("зуби", page=1, new_count=0, page_cap=3)   # dry #1 -> page 2
    st.record_page_result("зуби", page=2, new_count=5, page_cap=3)   # productive -> page 3, dry=0
    assert st.current_page("зуби") == 3
    st.record_page_result("зуби", page=3, new_count=0, page_cap=3)   # dry #1 again (not #2) -> reset (cap)
    assert st.current_page("зуби") == 1


def test_record_page_productive_at_cap_resets(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_page_result("зуби", page=3, new_count=4, page_cap=3)   # productive at cap
    assert st.current_page("зуби") == 1                              # reset, re-scan next TTL cycle


def test_record_page_dry_at_cap_stops(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_page_result("зуби", page=3, new_count=0, page_cap=3)   # first dry but already at cap
    assert st.current_page("зуби") == 1                              # do not probe past the cap


def test_phrase_pages_persist(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.record_page_result("готель", page=1, new_count=2, page_cap=3)
    reloaded = SearchState.load(path)
    assert reloaded.current_page("готель") == 2


def test_legacy_state_without_phrase_pages_loads(tmp_path):
    import json as _json
    path = tmp_path / "partial.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "grid_cursor": 3,
                                 "next_allowed_at": 0.0, "backends": {}, "cache": {}}),
                    encoding="utf-8")
    st = SearchState.load(str(path), clock=Clock())
    assert st.current_page("будь-що") == 1        # missing key defaults cleanly


def test_soonest_recovery_min_over_nonquarantined_with_floor(tmp_path):
    clock = Clock(1000.0)
    st = SearchState(str(tmp_path / "s.json"), clock=clock)
    # yahoo cooled 100s out, brave cooled 900s out; floor 300 → min(100,900) clamped to 300
    st._data["backends"] = {
        "yahoo": {"fails": 1, "cooldown_until": 1100.0, "quarantined_until": 0.0, "next_reprobe_at": 0.0},
        "brave": {"fails": 2, "cooldown_until": 1900.0, "quarantined_until": 0.0, "next_reprobe_at": 0.0},
    }
    assert st.soonest_recovery(["yahoo", "brave"], floor=300.0) == 300.0
    # raise yahoo cooldown above floor → min wins
    st._data["backends"]["yahoo"]["cooldown_until"] = 1500.0  # 500s out
    assert st.soonest_recovery(["yahoo", "brave"], floor=300.0) == 500.0


def test_record_yield_tracks_tries_ewma_and_dry_streak(tmp_path):
    s = SearchState(str(tmp_path / "state.json"), clock=lambda: 1000.0)
    s.record_yield("знижка військові", 4, alpha=0.5)
    e = s._data["phrase_stats"][s._key("знижка військові")]
    assert e["tries"] == 1
    assert e["ewma"] == 2.0            # 0.5*0 + 0.5*4
    assert e["dry_streak"] == 0

    s.record_yield("знижка військові", 0, alpha=0.5)
    e = s._data["phrase_stats"][s._key("знижка військові")]
    assert e["tries"] == 2
    assert e["ewma"] == 1.0            # 0.5*2 + 0.5*0
    assert e["dry_streak"] == 1        # a dry pass increments the streak


def test_record_yield_survives_reload(tmp_path):
    p = str(tmp_path / "state.json")
    SearchState(p, clock=lambda: 1.0).record_yield("акція ЗСУ", 3)
    reloaded = SearchState.load(p, clock=lambda: 2.0)
    assert reloaded._data["phrase_stats"][reloaded._key("акція ЗСУ")]["tries"] == 1


def test_effective_ttl_explores_young_phrases(tmp_path):
    s = _state(tmp_path, Clock())
    s.record_yield("рідкісна фраза", 0)          # tries=1 < cold_tries
    assert s.effective_ttl("рідкісна фраза", 100.0, cold_tries=3) == 100.0


def test_effective_ttl_keeps_base_for_productive(tmp_path):
    s = _state(tmp_path, Clock())
    for _ in range(5):
        s.record_yield("врожайна", 3)            # ewma stays > 0
    assert s.effective_ttl("врожайна", 100.0, cold_tries=3) == 100.0


def test_effective_ttl_backs_off_warm_dry_phrase_capped(tmp_path):
    s = _state(tmp_path, Clock())
    for _ in range(10):
        s.record_yield("суха фраза", 0)          # tries=10, ewma=0, dry_streak=10
    ttl = s.effective_ttl("суха фраза", 100.0, cold_tries=3, mult_cap=8.0)
    assert ttl == 800.0                          # capped at base * mult_cap


def test_effective_ttl_unknown_phrase_is_base(tmp_path):
    s = _state(tmp_path, Clock())
    assert s.effective_ttl("невидана", 100.0) == 100.0


def test_effective_ttl_backs_off_once_yielded_then_dry_phrase(tmp_path):
    """Регресія: фраза, що дала урожай ОДИН раз давно, а потім довго суха, має
    зрештою повернутись у backoff — інакше «retire once-good-now-dry» ніколи не
    спрацьовує, бо EWMA лише асимптотично наближається до 0 (ніколи рівно 0.0)."""
    s = _state(tmp_path, Clock())
    s.record_yield("разова знахідка", 2)          # один реальний урожай...
    for _ in range(10):
        s.record_yield("разова знахідка", 0)      # ...потім довго суха (10 проходів)
    ttl = s.effective_ttl("разова знахідка", 100.0, cold_tries=3)
    assert ttl > 100.0                             # має повернутись у backoff, не залишитись base


def test_host_freq_and_coverage_counts(tmp_path):
    s = _state(tmp_path, Clock())
    for h in ["a.ua", "a.ua", "a.ua", "b.ua", "b.ua", "c.ua", "d.ua"]:
        s.note_host(h)
    # a=3 (neither), b=2 (doubleton), c=1, d=1 (singletons)
    observed, f1, f2 = s.coverage_counts()
    assert observed == 4
    assert f1 == 2            # c, d
    assert f2 == 1            # b


def test_note_host_ignores_empty(tmp_path):
    s = _state(tmp_path, Clock())
    s.note_host("")
    s.note_host(None)         # type: ignore[arg-type]
    assert s.coverage_counts() == (0, 0, 0)


def _counting_save(state):
    """Wrap state._save so we can assert on the number of persist calls."""
    calls = []
    orig = state._save
    def counting():
        calls.append(1)
        orig()
    state._save = counting
    return calls


def test_record_yields_batch_matches_per_item_and_saves_once(tmp_path):
    per = SearchState(str(tmp_path / "per.json"), clock=lambda: 1000.0)
    batch = SearchState(str(tmp_path / "batch.json"), clock=lambda: 1000.0)
    data = {"фраза А": 3, "фраза Б": 0, "фраза В": 5}
    for k, v in data.items():
        per.record_yield(k, v, alpha=0.3)

    calls = _counting_save(batch)
    batch.record_yields(data, alpha=0.3)

    assert len(calls) == 1                                    # ONE _save() for the whole batch
    assert batch._data["phrase_stats"] == per._data["phrase_stats"]


def test_record_yields_advances_dry_streak_for_zero_yield_entries(tmp_path):
    s = _state(tmp_path, Clock())
    s.record_yields({"суха фраза": 0})
    e = s._data["phrase_stats"][s._key("суха фраза")]
    assert e["tries"] == 1
    assert e["dry_streak"] == 1                                # 0-yield entries still advance


def test_note_hosts_batch_matches_per_item_and_saves_once(tmp_path):
    per = SearchState(str(tmp_path / "per.json"), clock=Clock())
    batch = SearchState(str(tmp_path / "batch.json"), clock=Clock())
    hosts = ["a.ua", "a.ua", "b.ua", "", None, "c.ua"]
    for h in hosts:
        per.note_host(h)

    calls = _counting_save(batch)
    batch.note_hosts(hosts)

    assert len(calls) == 1                                     # ONE _save() for the whole batch
    assert batch._data["host_freq"] == per._data["host_freq"]


def test_note_hosts_prunes_singletons_over_cap(tmp_path, monkeypatch):
    import crawler.discovery.search_state as ss_mod
    monkeypatch.setattr(ss_mod, "_HOST_FREQ_CAP", 3)
    s = _state(tmp_path, Clock())
    # 2 doubletons (never pruned) + 3 singletons -> 5 entries, over the cap of 3
    s.note_hosts(["d1.ua", "d1.ua", "d2.ua", "d2.ua", "s1.ua", "s2.ua", "s3.ua"])
    freq = s._data["host_freq"]
    assert len(freq) <= 3                                      # pruned back down toward the cap
    assert freq.get("d1.ua") == 2 and freq.get("d2.ua") == 2   # doubletons always survive
    observed, f1, f2 = s.coverage_counts()
    assert observed == len(freq)
    assert f2 == 2                                             # both doubletons retained
