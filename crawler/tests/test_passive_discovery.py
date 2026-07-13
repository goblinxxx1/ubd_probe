from crawler.discovery.passive import extract_source_candidates, normalize_ref
from crawler.models import RawItem


def test_extracts_new_handles_and_skips_known():
    item = RawItem(
        source_id=1, platform="telegram", key="k",
        text="Знижки тут: підпишись @newshop і дивись instagram.com/coolcafe",
        links=["https://t.me/knownchan", "https://facebook.com/vetclub"],
    )
    known = {normalize_ref("telegram", "t.me/knownchan")}
    cands = extract_source_candidates(item, known)
    refs = {(c.type, normalize_ref(c.type, c.url_or_handle)) for c in cands}

    assert ("telegram", "newshop") in refs
    assert ("instagram", "coolcafe") in refs
    assert ("facebook", "vetclub") in refs
    assert ("telegram", "knownchan") not in refs  # filtered as known
    assert all(c.discovered_from_source_id == 1 for c in cands)


def test_no_candidates_when_all_known():
    item = RawItem(source_id=1, platform="website", key="k", text="plain text", links=[])
    assert extract_source_candidates(item, set()) == []
