import os

from crawler.config import load_config


def test_load_config_parses_accounts_and_flags(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_URL", "http://api")
    monkeypatch.setenv("CRAWLER_API_KEY", "k")
    monkeypatch.setenv("ACTIVE_DISCOVERY", "true")
    monkeypatch.setenv("INSTAGRAM_ACCOUNTS", "bot_a:pw1,bot_b:pw2")
    monkeypatch.setenv("FACEBOOK_ACCOUNTS", "")
    monkeypatch.setenv("PROXIES", "instagram=http://p1")

    cfg = load_config()
    assert cfg.internal_api_url == "http://api"
    assert cfg.active_discovery is True
    assert cfg.extractor == "heuristic"
    igs = [b for b in cfg.bot_accounts if b.platform == "instagram"]
    assert [b.username for b in igs] == ["bot_a", "bot_b"]
    assert igs[0].password == "pw1"
    assert cfg.proxies["instagram"] == "http://p1"
