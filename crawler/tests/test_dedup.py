from crawler.dedup import content_hash


def test_hash_is_stable_and_normalized():
    a = content_hash("20%  OFF", "Shop", "Body   text")
    b = content_hash("20% off", "shop", "body text")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_hash_distinguishes_content():
    assert content_hash("A", "S", "x") != content_hash("B", "S", "x")
