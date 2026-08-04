from crawler.discovery.query_grid import (
    AUDIENCE_FORMS, INTENT_FORMS, GRID_CITIES, GEO_INTENTS, GEO_AUDIENCES,
    build_grid, merge_queries)


def test_grid_size_is_base_plus_geo_block():
    base = len(INTENT_FORMS) * len(AUDIENCE_FORMS)          # 351
    geo = len(GEO_INTENTS) * len(GEO_AUDIENCES) * len(GRID_CITIES)  # 5*6*45 = 1350
    grid = build_grid()
    assert base == 351 and geo == 1350
    assert len(grid) == base + geo == 1701


def test_base_prefix_is_byte_stable():
    # first 351 == the plain intent×audience grid, unchanged order
    grid = build_grid()
    plain = build_grid(cities=[])
    assert len(plain) == 351
    assert grid[:351] == plain


def test_geo_block_present_and_ordered():
    grid = build_grid()
    assert "знижка військові Київ" in grid                  # {geo_intent} {geo_aud} {city}
    assert "знижка військові" in grid                       # plain base still present
    # geo entries carry a curated city suffix
    assert grid[351].endswith(f" {GRID_CITIES[0]}")
    assert grid[351] == f"{GEO_INTENTS[0]} {GEO_AUDIENCES[0]} {GRID_CITIES[0]}"


def test_grid_cities_curated_and_no_occupied():
    assert len(GRID_CITIES) == 45
    assert len(set(GRID_CITIES)) == 45                      # unique
    for occ in ("Донецьк", "Луганськ", "Сімферополь", "Севастополь",
                "Маріуполь", "Мелітополь", "Бердянськ"):
        assert occ not in GRID_CITIES


def test_geo_subsets_are_subsets_of_axes():
    assert set(GEO_INTENTS) <= set(INTENT_FORMS)
    assert set(GEO_AUDIENCES) <= set(AUDIENCE_FORMS)


def test_cities_di_controls_geo_size():
    grid = build_grid(cities=["Львів", "Одеса"])
    assert len(grid) == 351 + len(GEO_INTENTS) * len(GEO_AUDIENCES) * 2   # 351 + 60


def test_grid_has_intent_templates_not_brands():
    grid = build_grid()
    assert "знижка військові" in grid           # {intent} {audience}
    assert "OKKO ветерани" not in grid          # brands removed from the query axis
    assert "Rozetka військові" not in grid


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
