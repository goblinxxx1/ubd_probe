import json

from crawler.discovery.blocklist import is_blocked_host, reload_lang_blocked
from crawler.discovery.lang_block import LangBlockStore


def teardown_function():
    reload_lang_blocked(None)   # keep module-global blocklist clean between tests


def test_reload_lang_blocked_makes_host_blocked():
    reload_lang_blocked({"justcolor.net"})
    assert is_blocked_host("justcolor.net") is True
    assert is_blocked_host("https://www.justcolor.net/enfants") is True
    assert is_blocked_host("sub.justcolor.net") is True     # suffix match
    assert is_blocked_host("shop.ua") is False


def test_reload_lang_blocked_empty_clears():
    reload_lang_blocked({"justcolor.net"})
    reload_lang_blocked(None)
    assert is_blocked_host("justcolor.net") is False


def test_store_add_persists_and_blocks(tmp_path):
    path = tmp_path / "lang_blocked_hosts.json"
    store = LangBlockStore(str(path)).load()
    assert store.add("https://www.justcolor.net/enfants") is True   # url -> bare host
    assert "justcolor.net" in store.hosts()
    assert is_blocked_host("justcolor.net") is True                 # live-blocked after add
    assert json.loads(path.read_text(encoding="utf-8")) == ["justcolor.net"]


def test_store_add_duplicate_is_noop(tmp_path):
    store = LangBlockStore(str(tmp_path / "l.json")).load()
    assert store.add("justcolor.net") is True
    assert store.add("https://justcolor.net/other") is False        # same bare host


def test_store_load_existing_file_blocks(tmp_path):
    path = tmp_path / "l.json"
    path.write_text(json.dumps(["justcolor.net", "example.com"]), encoding="utf-8")
    LangBlockStore(str(path)).load()
    assert is_blocked_host("justcolor.net") is True
    assert is_blocked_host("example.com") is True


def test_store_missing_file_is_empty(tmp_path):
    store = LangBlockStore(str(tmp_path / "nope.json")).load()
    assert store.hosts() == frozenset()
    assert is_blocked_host("justcolor.net") is False


import threading


def test_lang_block_add_is_thread_safe(tmp_path):
    from crawler.discovery.lang_block import LangBlockStore
    s = LangBlockStore(str(tmp_path / "lang.json"))
    n = 200

    def worker(i):
        s.add(f"h{i}.by")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s.hosts()) == n
    import json
    with open(str(tmp_path / "lang.json"), encoding="utf-8") as f:
        assert len(json.load(f)) == n
