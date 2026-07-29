from crawler.discovery.city_axis import CityAxis


def _axis():
    return CityAxis(["Київ", "Львів", "Одеса"])


def test_suffixes_current_city_onto_phrases():
    out, cur = _axis().next_batch(["знижка військовим", "акція ветеранам"], cursor=0, k=2)
    assert out == ["знижка військовим Київ", "акція ветеранам Київ"]
    assert cur == 1


def test_k_caps_phrase_count():
    out, _ = _axis().next_batch(["a", "b", "c"], cursor=1, k=2)
    assert out == ["a Львів", "b Львів"]


def test_cursor_advances_and_wraps():
    out, cur = _axis().next_batch(["x"], cursor=2, k=1)   # last city
    assert out == ["x Одеса"]
    assert cur == 0                                       # wrapped to start


def test_out_of_range_and_negative_cursor_normalised():
    assert _axis().next_batch(["x"], cursor=5, k=1)[0] == ["x Одеса"]    # 5 % 3 == 2
    assert _axis().next_batch(["x"], cursor=-1, k=1)[0] == ["x Одеса"]   # -1 % 3 == 2


def test_k_zero_returns_empty_and_holds_cursor():
    out, cur = _axis().next_batch(["x"], cursor=1, k=0)
    assert out == [] and cur == 1


def test_empty_gazetteer_is_byte_eq_off():
    out, cur = CityAxis([]).next_batch(["x"], cursor=0, k=3)
    assert out == [] and cur == 0


def test_skips_empty_phrases():
    out, _ = _axis().next_batch(["", "  ", "реальна"], cursor=0, k=3)
    assert out == ["реальна Київ"]


def test_deterministic():
    a = _axis()
    assert a.next_batch(["p"], 0, 1) == a.next_batch(["p"], 0, 1)


def test_default_loads_gazetteer():
    assert len(CityAxis()) > 1000        # газетир ~1229 назв
