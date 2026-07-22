from crawler.discovery.brand_feed import BRAND_SEEDS
from crawler.discovery.query_grid import BRANDS


def test_brand_seeds_cover_exactly_the_brand_set():
    assert set(BRAND_SEEDS) == set(BRANDS)


def test_brand_seeds_have_bare_nonempty_fallback_domains():
    for brand, (qid, domain) in BRAND_SEEDS.items():
        assert domain and domain.strip(), brand
        assert " " not in domain and "/" not in domain, brand   # bare host, no scheme/path
        assert qid is None or qid.startswith("Q"), brand
