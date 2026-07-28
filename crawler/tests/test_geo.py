from crawler.discovery.geo import build_lookup, find_cities, find_city, is_online

FIX = [
    {"name": "Львів", "forms": [{"f": "львів", "m": 0}, {"f": "львові", "m": 0}, {"f": "lviv", "m": 0}]},
    {"name": "Суми", "forms": [{"f": "суми", "m": 1}, {"f": "сумах", "m": 0}, {"f": "sumy", "m": 0}]},
    {"name": "Біла Церква", "forms": [{"f": "біла церква", "m": 0}, {"f": "білій церкві", "m": 0}]},
]
LK, MAXN = build_lookup(FIX)


def _f(text):
    return find_cities(text, LK, MAXN)


def test_permissive_match_in_prose():
    assert _f("Акція діє у Львові") == ["Львів"]


def test_transliteration_maps_to_canonical():
    assert _f("Discount in Lviv only") == ["Львів"]


def test_marker_only_form_not_matched_as_bare_word():
    assert _f("Виграйте великі суми грошей") == []


def test_marker_only_form_matched_with_marker():
    assert _f("Наш заклад: м. Суми, центр") == ["Суми"]


def test_permissive_oblique_of_vetoed_city_still_matches():
    assert _f("Знижки для військових у Сумах") == ["Суми"]


def test_multiword_name_with_marker():
    assert _f("м. Біла Церква, вул. Шевченка") == ["Біла Церква"]


def test_multi_return_first_appearance_order():
    assert _f("Спершу у Львові, а також м. Суми") == ["Львів", "Суми"]


def test_find_city_single_and_none():
    assert find_city("у Львові") == "Львів"
    assert _f("немає міста") == []


def test_online_signal_unchanged():
    assert is_online("Працюємо онлайн по всій Україні")
    assert not is_online("Знижка у кафе на вулиці")


def test_default_file_detects_major_city():
    assert "Київ" in find_cities("Велика знижка у Києві для ветеранів")
