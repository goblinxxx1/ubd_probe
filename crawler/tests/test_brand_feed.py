from crawler.discovery.brand_feed import BRAND_SEEDS, BrandDomainCache
from crawler.discovery.query_grid import BRANDS


def test_brand_seeds_cover_exactly_the_brand_set():
    assert set(BRAND_SEEDS) == set(BRANDS)


def test_brand_seeds_have_bare_nonempty_fallback_domains():
    for brand, (qid, domain) in BRAND_SEEDS.items():
        assert domain and domain.strip(), brand
        assert " " not in domain and "/" not in domain, brand   # bare host, no scheme/path
        assert qid is None or qid.startswith("Q"), brand


def test_cache_defaults_empty_and_stale(tmp_path):
    c = BrandDomainCache.load(str(tmp_path / "b.json"))
    assert c.domains() == {}
    assert c.is_stale(3600) is True


def test_cache_replace_persists_and_reloads(tmp_path):
    path = str(tmp_path / "b.json")
    BrandDomainCache.load(path, clock=lambda: 1000.0).replace({"OKKO": "okko.ua"})
    assert BrandDomainCache.load(path).domains() == {"OKKO": "okko.ua"}


def test_cache_freshness_gate(tmp_path):
    now = {"t": 1000.0}
    c = BrandDomainCache.load(str(tmp_path / "b.json"), clock=lambda: now["t"])
    c.replace({"OKKO": "okko.ua"})
    assert c.is_stale(3600) is False        # just refreshed
    now["t"] = 1000.0 + 3600
    assert c.is_stale(3600) is True         # ttl elapsed


def test_cache_tolerates_corrupt_file(tmp_path):
    path = tmp_path / "b.json"
    path.write_text("{ not json", encoding="utf-8")
    assert BrandDomainCache.load(str(path)).domains() == {}
