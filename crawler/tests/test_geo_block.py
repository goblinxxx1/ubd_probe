import json

from crawler.discovery.blocklist import is_blocked_host, reload_geo_blocked
from crawler.discovery.geo_block import GeoBlockStore


def teardown_function():
    reload_geo_blocked(None)   # keep module-global blocklist clean between tests


def test_reload_geo_blocked_makes_host_blocked():
    reload_geo_blocked({"restoran.cafe"})
    assert is_blocked_host("restoran.cafe") is True
    assert is_blocked_host("https://restoran.cafe/spb") is True
    assert is_blocked_host("sub.restoran.cafe") is True     # suffix match, like LEARNED
    assert is_blocked_host("other.com") is False


def test_reload_geo_blocked_empty_clears():
    reload_geo_blocked({"restoran.cafe"})
    reload_geo_blocked(None)
    assert is_blocked_host("restoran.cafe") is False


def test_store_add_persists_and_blocks(tmp_path):
    path = tmp_path / "geo_blocked_hosts.json"
    store = GeoBlockStore(str(path)).load()
    assert store.add("https://restoran.cafe/spb") is True     # url -> bare host
    assert "restoran.cafe" in store.hosts()
    assert is_blocked_host("restoran.cafe") is True           # live-blocked after add
    assert json.loads(path.read_text(encoding="utf-8")) == ["restoran.cafe"]


def test_store_add_duplicate_is_noop(tmp_path):
    path = tmp_path / "geo.json"
    store = GeoBlockStore(str(path)).load()
    assert store.add("restoran.cafe") is True
    assert store.add("https://restoran.cafe/other") is False  # same bare host, no re-write


def test_store_load_existing_file_blocks(tmp_path):
    path = tmp_path / "geo.json"
    path.write_text(json.dumps(["restoran.cafe", "shop.com"]), encoding="utf-8")
    GeoBlockStore(str(path)).load()
    assert is_blocked_host("restoran.cafe") is True
    assert is_blocked_host("shop.com") is True


def test_store_missing_file_is_empty(tmp_path):
    store = GeoBlockStore(str(tmp_path / "nope.json")).load()
    assert store.hosts() == frozenset()
    assert is_blocked_host("restoran.cafe") is False


import threading


def test_geo_block_add_is_thread_safe(tmp_path):
    from crawler.discovery.geo_block import GeoBlockStore
    s = GeoBlockStore(str(tmp_path / "geo.json"))
    n = 200

    def worker(i):
        s.add(f"h{i}.ru")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s.hosts()) == n           # none lost
    import json
    with open(str(tmp_path / "geo.json"), encoding="utf-8") as f:
        assert len(json.load(f)) == n    # file valid + complete
