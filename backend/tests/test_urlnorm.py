# backend/tests/test_urlnorm.py
from app.core.urlnorm import canonicalize_target_url


def test_strips_www_and_collapses_scheme():
    assert canonicalize_target_url("https://www.okko.ua/promo") == "okko.ua/promo"
    assert canonicalize_target_url("http://okko.ua/promo") == "okko.ua/promo"


def test_strips_utm_and_click_ids():
    assert canonicalize_target_url(
        "https://www.okko.ua/promo/?utm_source=fb&fbclid=xxx&gclid=y") == "okko.ua/promo"


def test_keeps_meaningful_query_sorted():
    assert canonicalize_target_url("https://shop.ua/p?b=2&a=1&utm_x=9") == "shop.ua/p?a=1&b=2"


def test_trailing_slash_and_root_collapse():
    assert canonicalize_target_url("https://okko.ua/") == "okko.ua"
    assert canonicalize_target_url("https://okko.ua") == "okko.ua"


def test_strips_port_and_userinfo():
    assert canonicalize_target_url("https://user:pw@www.okko.ua:443/p") == "okko.ua/p"


def test_non_http_and_junk_and_empty_return_none():
    assert canonicalize_target_url("ftp://okko.ua/x") is None
    assert canonicalize_target_url("mailto:a@b.com") is None
    assert canonicalize_target_url("not a url") is None
    assert canonicalize_target_url("") is None
