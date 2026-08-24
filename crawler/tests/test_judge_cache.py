from crawler.judge.base import Verdict
from crawler.judge.cache import VerdictCache


def test_put_get_roundtrip_and_persist(tmp_path):
    path = str(tmp_path / "judge_cache.json")
    c = VerdictCache(path)
    assert c.get("h1") is None
    c.put("h1", Verdict(genuine=False, page_scoped=True, reason="song title"))
    got = c.get("h1")
    assert got is not None and got.genuine is False and got.reason == "song title"
    # persisted -> a fresh instance reads it back
    c2 = VerdictCache(path)
    got2 = c2.get("h1")
    assert got2 is not None and got2.genuine is False and got2.page_scoped is True


def test_corrupt_file_starts_empty(tmp_path):
    path = str(tmp_path / "judge_cache.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not json")
    c = VerdictCache(path)
    assert c.get("anything") is None      # corrupt -> clean start, no crash
