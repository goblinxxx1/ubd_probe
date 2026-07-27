# crawler/tests/test_aggregator_feed.py
from crawler.discovery.aggregator_feed import AggregatorDomainStore, AggregatorDomainFeed
from crawler.discovery.passive import normalize_ref


def test_add_unions_dedups_and_persists(tmp_path):
    path = str(tmp_path / "agg.json")
    s = AggregatorDomainStore.load(path)
    assert s.domains() == []
    s.add({"b.ua", "a.ua"}, cap=10)          # sorted on insert
    s.add({"a.ua", "c.ua"}, cap=10)          # a.ua deduped, c.ua appended
    assert AggregatorDomainStore.load(path).domains() == ["a.ua", "b.ua", "c.ua"]


def test_add_keeps_newest_cap(tmp_path):
    s = AggregatorDomainStore.load(str(tmp_path / "agg.json"))
    s.add({"a.ua"}, cap=2)
    s.add({"b.ua"}, cap=2)
    s.add({"c.ua"}, cap=2)                    # over cap → oldest (a.ua) dropped
    assert s.domains() == ["b.ua", "c.ua"]


def test_add_ignores_empty(tmp_path):
    s = AggregatorDomainStore.load(str(tmp_path / "agg.json"))
    s.add({"", "a.ua"}, cap=10)
    assert s.domains() == ["a.ua"]


def test_cursor_defaults_zero_and_persists(tmp_path):
    path = str(tmp_path / "agg.json")
    s = AggregatorDomainStore.load(path)
    assert s.cursor() == 0
    s.set_cursor(4)
    assert AggregatorDomainStore.load(path).cursor() == 4


def test_load_tolerates_corrupt(tmp_path):
    p = tmp_path / "agg.json"
    p.write_text("{ not json", encoding="utf-8")
    assert AggregatorDomainStore.load(str(p)).domains() == []


def _store(tmp_path, hosts):
    s = AggregatorDomainStore.load(str(tmp_path / "agg.json"))
    s.add(set(hosts), cap=100)
    return s


def test_feed_emits_website_candidates(tmp_path):
    feed = AggregatorDomainFeed(_store(tmp_path, ["okko.ua"]))
    c = feed.candidates(known=set())[0]
    assert c.type == "website"
    assert c.url_or_handle == "https://okko.ua"
    assert c.discovery_note == "aggregator-feed:okko.ua"


def test_feed_skips_known_and_empty(tmp_path):
    feed = AggregatorDomainFeed(_store(tmp_path, ["okko.ua"]))
    known = {normalize_ref("website", "https://okko.ua")}
    assert feed.candidates(known) == []
    empty = AggregatorDomainFeed(AggregatorDomainStore.load(str(tmp_path / "e.json")))
    assert empty.candidates(known=set()) == []


def test_feed_rotates_window(tmp_path):
    # note: store keeps insertion order; add sorts each batch, so a,b,c,d
    feed = AggregatorDomainFeed(_store(tmp_path, ["a.ua", "b.ua", "c.ua", "d.ua"]), per_pass=2)
    assert [c.name for c in feed.candidates(set())] == ["a.ua", "b.ua"]
    assert [c.name for c in feed.candidates(set())] == ["c.ua", "d.ua"]
    assert [c.name for c in feed.candidates(set())] == ["a.ua", "b.ua"]
