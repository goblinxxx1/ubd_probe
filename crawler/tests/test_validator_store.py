from crawler.discovery.validator_store import ValidatorStore


def test_put_get_roundtrip(tmp_path):
    s = ValidatorStore(str(tmp_path / "v.json"))
    s.put("https://a.ua", etag='"abc"', last_modified="Wed, 21 Oct 2026 07:28:00 GMT")
    assert s.get("https://a.ua") == {"etag": '"abc"',
                                     "last_modified": "Wed, 21 Oct 2026 07:28:00 GMT"}
    assert s.get("https://missing.ua") is None
