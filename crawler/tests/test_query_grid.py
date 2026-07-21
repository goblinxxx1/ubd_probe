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
