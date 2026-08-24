import threading

from crawler.util.locked_set import LockedSet


def test_locked_set_basic_contains_and_add():
    s = LockedSet({"a"})
    assert "a" in s
    assert "b" not in s
    s.add("b")
    assert "b" in s
    assert len(s) == 2


def test_locked_set_concurrent_add_dedups():
    s = LockedSet()
    n = 500

    def worker():
        for _ in range(n):
            s.add("dup")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s) == 1
