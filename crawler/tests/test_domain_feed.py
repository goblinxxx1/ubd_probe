from crawler.discovery.domain_feed import DomainFeed
from crawler.discovery.domain_registry import DomainRegistry


def _reg(tmp_path):
    return DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0, promote_min_score=0.5)


def test_emits_top_domains_as_website_candidates(tmp_path):
    r = _reg(tmp_path)
    r.record("hi.ua", offers=3, errors=0)
    r.record("mid.ua", offers=1, errors=0)
    cands = DomainFeed(r, per_pass=8).candidates(known_hosts=set())
    assert [c.url_or_handle for c in cands] == ["https://hi.ua", "https://mid.ua"]
    assert all(c.type == "website" for c in cands)
    assert cands[0].name == "hi.ua"
    assert cands[0].discovery_note == "domain-rating:hi.ua"


def test_skips_known_hosts(tmp_path):
    r = _reg(tmp_path)
    r.record("hi.ua", offers=3, errors=0)
    r.record("mid.ua", offers=1, errors=0)
    cands = DomainFeed(r, per_pass=8).candidates(known_hosts={"hi.ua"})
    assert [c.url_or_handle for c in cands] == ["https://mid.ua"]


def test_respects_per_pass_cap(tmp_path):
    r = _reg(tmp_path)
    for i in range(5):
        r.record(f"d{i}.ua", offers=i + 1, errors=0)
    cands = DomainFeed(r, per_pass=2).candidates(known_hosts=set())
    assert len(cands) == 2


def test_empty_registry_returns_empty(tmp_path):
    assert DomainFeed(_reg(tmp_path), per_pass=8).candidates(set()) == []
