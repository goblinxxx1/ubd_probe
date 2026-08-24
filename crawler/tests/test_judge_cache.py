import threading

from crawler.judge.base import Verdict
from crawler.judge.cache import VerdictCache


def test_put_get_roundtrip_and_persist(tmp_path):
    path = str(tmp_path / "judge_cache.json")
    c = VerdictCache(path)
    assert c.get("h1") is None
    c.put("h1", Verdict(genuine=False, page_scoped=True, reason="song title"))
    got = c.get("h1")
    assert got is not None and got.genuine is False and got.reason == "song title"
    # персистентність -> новий інстанс читає збережене
    c2 = VerdictCache(path)
    got2 = c2.get("h1")
    assert got2 is not None and got2.genuine is False and got2.page_scoped is True


def test_corrupt_file_starts_empty(tmp_path):
    path = str(tmp_path / "judge_cache.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not json")
    c = VerdictCache(path)
    assert c.get("anything") is None      # биті дані -> чистий старт, без падіння


def test_put_is_thread_safe_no_corruption(tmp_path):
    path = str(tmp_path / "judge_cache.json")
    c = VerdictCache(path)
    n = 200
    def worker(i):
        c.put(f"h{i}", Verdict(genuine=bool(i % 2), page_scoped=True, reason=f"r{i}"))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads: t.start()
    for t in threads: t.join()
    # файл валідний JSON і всі ключі збереглися
    import json
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == n
    # перечитується наново
    assert VerdictCache(path).get("h1") is not None
