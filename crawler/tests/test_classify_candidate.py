import pytest

from crawler.discovery.providers import classify_candidate


@pytest.mark.parametrize("url, expected_type", [
    ("https://t.me/veteranychat", "telegram"),
    ("https://t.me/s/veteranychat", "telegram"),
    ("https://www.instagram.com/some_profile", "instagram"),
    ("https://facebook.com/somebiz", "facebook"),
    ("https://fb.com/somebiz", "facebook"),
    ("https://shop.example.com/deal", "website"),
])
def test_classifies_type_from_host(url, expected_type):
    result = classify_candidate(url)
    assert result is not None
    assert result[0] == expected_type


@pytest.mark.parametrize("url", [
    "https://instagram.com/p/AbC123",
    "https://instagram.com/reel/xyz",
    "https://instagram.com/explore/tags/x",
    "https://instagram.com/",
    "https://facebook.com/share/abc",
    "https://facebook.com/sharer/x",
    "https://facebook.com/",
    "not-a-url",
    "",
])
def test_reserved_or_invalid_returns_none(url):
    assert classify_candidate(url) is None


def test_returns_normalised_url_as_handle_field():
    # host lowercased, utm stripped; path case preserved (paths are case-sensitive)
    t, uoh = classify_candidate("HTTPS://T.me/Chan?utm_source=x")
    assert t == "telegram"
    assert uoh == "https://t.me/Chan"
