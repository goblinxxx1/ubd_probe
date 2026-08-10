"""End-to-end regression: a search candidate that doesn't fit this pass's fetch
budget is NOT orphaned — it stays unharvested in the cache and re-surfaces next
pass, with no DDG re-search. Guards the invariant the whole track exists for."""

from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate


def _mark_consumed(st, cands, stop_index):
    """Mirror of Runner._mark_consumed_search_phrases: mark a phrase harvested
    only when ALL its candidates are at positions < stop_index."""
    last_pos = {}
    for i, c in enumerate(cands):
        if c.origin_key is not None:
            last_pos[c.origin_key] = i
    done = [k for k, pos in last_pos.items() if pos < stop_index]
    if done:
        st.mark_harvested(done)
    return done


def test_over_budget_candidates_survive_to_next_pass(tmp_path):
    # cache keys are casefold-normalized (case-insensitive dedup), so origin_key
    # comes back lowercased; use a lowercase phrase so the tag round-trips cleanly.
    phrase = "протезування зубів убд"
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    # phrase found 3 businesses last pass; the fetch budget only reached 1 of them.
    st.cache_put(phrase, [SourceCandidate(name=f"biz{i}", type="website",
                                          url_or_handle=f"https://biz{i}.ua") for i in range(3)])

    # pass 1: drain surfaces all 3; harvest stopped at index 1 (budget) -> phrase NOT fully done.
    cands = [c for _, cs in st.unharvested(10_000) for c in cs]
    assert [c.origin_key for c in cands] == [phrase, phrase, phrase]
    done = _mark_consumed(st, cands, stop_index=1)
    assert done == []                                     # 3 candidates, only 1 examined

    # pass 2: the phrase is STILL unharvested -> its candidates re-surface, no re-search.
    again = st.unharvested(10_000)
    assert [k for k, _ in again] == [phrase]
    assert len(again[0][1]) == 3


def test_fully_consumed_phrase_is_not_redrained(tmp_path):
    phrase = "шиномонтаж зсу"
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put(phrase, [SourceCandidate(name="only", type="website",
                                          url_or_handle="https://only.ua")])
    cands = [c for _, cs in st.unharvested(10_000) for c in cs]
    done = _mark_consumed(st, cands, stop_index=len(cands))   # whole phrase examined
    assert done == [phrase]
    assert st.unharvested(10_000) == []                       # done -> never re-drained
