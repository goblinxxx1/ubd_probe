from crawler.config import _split_csv


def test_split_csv_trims_and_drops_empty():
    assert _split_csv("a, b ,,c") == ["a", "b", "c"]
    assert _split_csv("") == []


def test_default_search_backends_are_valid_ddgs_engines():
    # Guard against ddgs upgrades silently invalidating a backend name: an unknown
    # name resolves to >1 engine (the "auto" fallback) and logs
    # "backend is not set. Using 'auto'". A valid single engine resolves to exactly 1.
    import logging
    from ddgs import DDGS
    from crawler.config import _RawSettings, from_settings
    logging.disable(logging.CRITICAL)
    ddgs = DDGS()
    for name in from_settings(_RawSettings()).search_backends:
        assert len(ddgs._get_engines("text", name)) == 1, f"{name!r} is not a valid ddgs engine"


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
