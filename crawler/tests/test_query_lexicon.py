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


def test_reload_none_or_missing_is_empty(tmp_path):
    ql.reload_learned(None)
    assert ql.learned_services() == ()
    ql.reload_learned(str(tmp_path / "nope.json"))
    assert ql.learned_services() == ()


def test_dedup_casefold(tmp_path):
    path = _write(tmp_path, [{"term": "Кава", "z": 2.0}, {"term": "кава", "z": 1.0}])
    ql.reload_learned(path)
    assert ql.learned_services() == ("Кава",)
