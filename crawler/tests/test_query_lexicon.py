import json

from crawler.discovery import query_lexicon as ql


def _write(tmp_path, entries):
    p = tmp_path / "q_learned.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return str(p)


def test_learned_services_categories_first_then_by_z(tmp_path):
    path = _write(tmp_path, [
        {"term": "автосервіс", "z": 4.0},
        {"term": "медицина", "source": "category"},
        {"term": "стоматологія", "z": 9.0},
    ])
    ql.reload_learned(path)
    assert ql.learned_services() == ("медицина", "стоматологія", "автосервіс")


def test_learned_services_split_separates_categories_and_mined(tmp_path):
    path = _write(tmp_path, [
        {"term": "автосервіс", "z": 4.0},
        {"term": "медицина", "source": "category"},
        {"term": "стоматологія", "z": 9.0},
    ])
    ql.reload_learned(path)
    cats, mined = ql.learned_services_split()
    assert cats == ("медицина",)
    assert mined == ("стоматологія", "автосервіс")   # by z desc


def test_compose_seed_first_and_mined_uncapped_when_cap_zero(tmp_path):
    path = _write(tmp_path, [{"term": f"m{i}", "z": float(100 - i)} for i in range(50)])
    ql.reload_learned(path)
    out = ql.compose_service_terms(("протезування зубів", "шиномонтаж"), cap=0)
    assert out[0] == "протезування зубів" and out[1] == "шиномонтаж"   # seed first
    assert sum(1 for x in out if x.startswith("m")) == 50             # miner uncapped


def test_compose_cap_applies_to_mined_only_never_seed_or_categories(tmp_path):
    path = _write(tmp_path,
                  [{"term": "медцентр", "source": "category"}]
                  + [{"term": f"m{i}", "z": float(100 - i)} for i in range(50)])
    ql.reload_learned(path)
    out = ql.compose_service_terms(("шиномонтаж",), cap=10)
    assert "шиномонтаж" in out          # seed always survives the cap
    assert "медцентр" in out            # category always survives the cap
    assert sum(1 for x in out if x.startswith("m")) == 10   # only mined is capped


def test_compose_dedups_seed_against_learned(tmp_path):
    path = _write(tmp_path, [{"term": "стоматологія", "source": "category"}])
    ql.reload_learned(path)
    out = ql.compose_service_terms(("Стоматологія", "шиномонтаж"), cap=0)
    assert out.count("Стоматологія") + out.count("стоматологія") == 1  # casefold dedup


def test_reload_none_or_missing_is_empty(tmp_path):
    ql.reload_learned(None)
    assert ql.learned_services() == ()
    ql.reload_learned(str(tmp_path / "nope.json"))
    assert ql.learned_services() == ()


def test_dedup_casefold(tmp_path):
    path = _write(tmp_path, [{"term": "Кава", "z": 2.0}, {"term": "кава", "z": 1.0}])
    ql.reload_learned(path)
    assert ql.learned_services() == ("Кава",)


def test_reload_wrong_shape_scalar_is_empty(tmp_path):
    p = tmp_path / "q_learned.json"
    p.write_text("42", encoding="utf-8")
    ql.reload_learned(str(p))
    assert ql.learned_services() == ()


def test_reload_wrong_shape_object_or_null_is_empty(tmp_path):
    p = tmp_path / "q_learned.json"
    p.write_text("null", encoding="utf-8")
    ql.reload_learned(str(p))
    assert ql.learned_services() == ()

    p2 = tmp_path / "q_learned2.json"
    p2.write_text(json.dumps({"term": "кава"}), encoding="utf-8")
    ql.reload_learned(str(p2))
    assert ql.learned_services() == ()
