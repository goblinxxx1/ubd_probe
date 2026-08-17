from crawler.config import _split_csv


def test_split_csv_trims_and_drops_empty():
    assert _split_csv("a, b ,,c") == ["a", "b", "c"]
    assert _split_csv("") == []


def test_backoff_hygiene_defaults():
    from crawler.config import _RawSettings, from_settings
    cfg = from_settings(_RawSettings())
    assert cfg.search_backend_quarantine_threshold == 6
    assert cfg.search_backend_quarantine_hours == 24.0
    assert cfg.search_backend_reprobe_hours == 6.0
    assert cfg.search_backoff_floor_seconds == 300.0
