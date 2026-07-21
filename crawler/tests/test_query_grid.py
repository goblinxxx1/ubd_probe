from crawler.discovery.query_grid import (
    AUDIENCE_FORMS, INTENT_FORMS, BRANDS, build_grid, merge_queries)


def test_grid_size_matches_axes():
    grid = build_grid()
    assert len(grid) == (len(INTENT_FORMS) + len(BRANDS)) * len(AUDIENCE_FORMS)


def test_grid_has_expected_templates():
    grid = build_grid()
    assert "знижка військові" in grid          # {intent} {audience}
    assert "OKKO ветерани" in grid              # {brand} {audience}


def test_grid_is_deduped_and_nonempty():
    grid = build_grid()
    assert grid == list(dict.fromkeys(grid))    # no duplicates, order preserved
    assert all(q.strip() for q in grid)         # no empty/whitespace entries


def test_grid_order_is_stable():
    assert build_grid() == build_grid()


def test_merge_queries_dedups_casefold_primary_first():
    merged = merge_queries(["знижка військові", "акція ЗСУ"], ["Акція ЗСУ", "мій пін"])
    assert merged == ["знижка військові", "акція ЗСУ", "мій пін"]


from crawler.discovery.query_grid import QueryGrid


def _tiny():
    return QueryGrid(["a", "b", "c", "d"])


def test_next_batch_advances_cursor():
    batch, cur = _tiny().next_batch(2, 0)
    assert batch == ["a", "b"]
    assert cur == 2


def test_next_batch_wraps_around_end():
    batch, cur = _tiny().next_batch(3, 3)   # d, a, b
    assert batch == ["d", "a", "b"]
    assert cur == 2


def test_full_sweep_visits_each_once():
    g = _tiny()
    seen, cur = [], 0
    for _ in range(len(g)):
        b, cur = g.next_batch(1, cur)
        seen += b
    assert sorted(seen) == ["a", "b", "c", "d"]
    assert cur == 0                          # back to start after a full sweep


def test_next_batch_clamps_bad_cursor_and_n():
    g = _tiny()
    assert g.next_batch(99, 0)[0] == ["a", "b", "c", "d"]   # n clamped to len
    assert g.next_batch(1, -5)[0] == ["a"]                  # negative cursor -> 0
    assert g.next_batch(1, 999)[0] == ["a"]                 # out-of-range cursor -> 0


def test_empty_grid_is_safe():
    batch, cur = QueryGrid([]).next_batch(5, 0)
    assert batch == [] and cur == 0
