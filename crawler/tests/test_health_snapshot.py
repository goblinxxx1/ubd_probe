from crawler.discovery.search_state import SearchState


def test_build_snapshot_summarizes_state(tmp_path):
    from crawler.discovery.health import build_snapshot
    now = 1000.0
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: now)
    # backends: brave healthy, duckduckgo blocked+quarantined
    st.record_success("brave")
    st.record_block("duckduckgo", 300.0, 21600.0, 0.0, lambda: 0.0,
                    quarantine_threshold=1, quarantine_seconds=3600.0, reprobe_seconds=1800.0)
    # phrases: one chronically dry (starved), one productive
    for _ in range(3):
        st.record_yield("суха фраза", 0)
    st.record_yield("жива фраза", 5)
    st.set_grid_cursor(42)
    st.cache_put("kw", [])
    st.note_hosts(["24tv.ua", "24tv.ua", "shop.ua"])
    st.set_global_backoff(120.0)

    snap = build_snapshot(st, pool=["brave", "duckduckgo"], now=now)

    beds = {b["name"]: b for b in snap["backends"]}
    assert beds["brave"]["status"] == "healthy"
    assert beds["duckduckgo"]["status"] == "quarantined"
    assert beds["duckduckgo"]["quarantine_s"] == 3600
    assert snap["global_backoff_s"] == 120
    assert snap["phrases"] == {"tracked": 2, "productive": 1, "starved": 1}
    assert snap["recall"]["grid_cursor"] == 42
    assert snap["recall"]["cache_entries"] == 1
    assert snap["noise_hosts"][0] == {"host": "24tv.ua", "count": 2}
    assert "generated_at" in snap


def test_build_snapshot_backend_order_follows_pool(tmp_path):
    from crawler.discovery.health import build_snapshot
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 0.0)
    snap = build_snapshot(st, pool=["startpage", "duckduckgo", "yahoo", "brave"], now=0.0)
    assert [b["name"] for b in snap["backends"]] == ["startpage", "duckduckgo", "yahoo", "brave"]
    # unseen backends default to healthy with no cooldown
    assert all(b["status"] == "healthy" for b in snap["backends"])
