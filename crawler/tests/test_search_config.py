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


def test_searxng_config_defaults():
    from crawler.config import _RawSettings, from_settings
    cfg = from_settings(_RawSettings())
    assert cfg.searxng_url == "http://searxng:8080"
    assert "yandex" not in cfg.searxng_engines   # project rule: never a Russian service
    # google/bing are verified live-working from our residential IP → intentionally enabled
    assert "google" in cfg.searxng_engines
    assert "bing" in cfg.searxng_engines
