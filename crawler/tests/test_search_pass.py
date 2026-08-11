from crawler.discovery.search_pass import SearchPass
from crawler.discovery.search_state import SearchState
from crawler.discovery.query_grid import QueryGrid
from crawler.models import SourceCandidate


class _Disc:
    """Fake ActiveDiscovery: records keyword lists, returns one candidate."""
    def __init__(self): self.calls = []
    def run(self, keywords, known):
        self.calls.append(list(keywords))
        return [SourceCandidate(name="c", type="website", url_or_handle="https://c.example")]


class _Plan:
    def __init__(self, include_pins, ok):
        self.discovery = _Disc(); self.include_pins = include_pins; self._ok = ok
    def succeeded(self): return self._ok


def _grid(): return QueryGrid([f"q{i}" for i in range(10)])


def test_single_provider_walks_block_from_grid_cursor_with_pins(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=True, ok=True)
    sp = SearchPass([ddg], st, _grid(), block_size=3, static_keywords=["пін"])
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1", "q2", "пін"]]
    assert st.grid_cursor == 3            # advanced by block_size on success


def test_cursor_advances_across_passes_and_wraps(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(6)])
    sp = SearchPass([ddg], st, grid, block_size=3)
    sp.run(set()); assert st.grid_cursor == 3
    sp.run(set()); assert st.grid_cursor == 0     # (3+3) % 6 wrap
    assert ddg.discovery.calls == [["q0", "q1", "q2"], ["q3", "q4", "q5"]]


def test_no_advance_when_provider_fails(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=True, ok=False)
    sp = SearchPass([ddg], st, _grid(), block_size=3)
    sp.run(set())
    assert st.grid_cursor == 0            # cursor frozen when the pass did not succeed


def test_provider_for_site_query_returns_single_discovery(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=True, ok=True)
    sp = SearchPass([ddg], st, _grid(), block_size=2)
    assert sp.provider_for_site_query() is ddg.discovery


def test_empty_grid_or_no_plans_is_noop(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=True, ok=True)
    assert SearchPass([], st, _grid(), block_size=3).run(set()) == []
    assert SearchPass([ddg], st, QueryGrid([]), block_size=3).run(set()) == []
    assert SearchPass([], st, _grid(), block_size=2).provider_for_site_query() is None


class _FreshState(SearchState):
    """SearchState with a preset fresh-phrase set for due-walking tests."""
    def __init__(self, path, fresh):
        super().__init__(path)
        self._fresh = set(fresh)
    def is_fresh(self, keyword, ttl_seconds):
        return keyword in self._fresh


def test_due_walking_skips_fresh_and_collects_due(tmp_path):
    st = _FreshState(str(tmp_path / "s.json"), fresh={"q0", "q1", "q3"})
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(6)])
    sp = SearchPass([ddg], st, grid, block_size=2, ttl_seconds=1000.0)
    sp.run(set())
    # q0,q1 fresh -> skip; q2 due -> take; q3 fresh -> skip; q4 due -> take (block_size=2)
    assert ddg.discovery.calls == [["q2", "q4"]]
    assert st.grid_cursor == 5              # advanced past all 5 scanned (q0..q4)


def test_due_walking_all_fresh_is_quiet_pass(tmp_path):
    st = _FreshState(str(tmp_path / "s.json"), fresh={f"q{i}" for i in range(4)})
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(4)])
    sp = SearchPass([ddg], st, grid, block_size=3, ttl_seconds=1000.0)
    sp.run(set())
    assert ddg.discovery.calls == [[]]      # nothing due -> empty keyword list
    assert st.grid_cursor == 0              # scanned whole grid, wrapped back to start


def test_ttl_zero_keeps_plain_walk(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(6)])
    sp = SearchPass([ddg], st, grid, block_size=3, ttl_seconds=0.0)
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1", "q2"]]
    assert st.grid_cursor == 3


def test_run_drains_unharvested_before_searching(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put("імплантація знижка військовим",
                 [SourceCandidate(name="giorno", type="website",
                                  url_or_handle="https://giorno-dentale.com")])
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(3)])
    sp = SearchPass([ddg], st, grid, block_size=2, ttl_seconds=10_000.0)
    out = sp.run(set())
    urls = [c.url_or_handle for c in out]
    assert urls[0] == "https://giorno-dentale.com"            # drained candidate comes FIRST
    assert out[0].origin_key == "імплантація знижка військовим"
    searched = [k for call in ddg.discovery.calls for k in call]
    assert "імплантація знижка військовим" not in searched    # its phrase was NOT re-searched
    assert ddg.discovery.calls == [["q0", "q1"]]              # new due phrases still searched


def test_drain_returns_unharvested_without_searching(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put("імплантація знижка убд",
                 [SourceCandidate(name="edclinic", type="website",
                                  url_or_handle="https://edclinic.com.ua")])
    ddg = _Plan(include_pins=False, ok=True)
    sp = SearchPass([ddg], st, QueryGrid([f"q{i}" for i in range(3)]),
                    block_size=2, ttl_seconds=10_000.0)
    out = sp.drain()
    assert [c.url_or_handle for c in out] == ["https://edclinic.com.ua"]
    assert out[0].origin_key == "імплантація знижка убд"
    assert ddg.discovery.calls == []            # drain must NOT call the provider


def test_drain_ttl_zero_is_empty(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put("kw", [SourceCandidate(name="x", type="website",
                                        url_or_handle="https://x.example")])
    sp = SearchPass([_Plan(False, True)], st, QueryGrid(["q0"]),
                    block_size=1, ttl_seconds=0.0)
    assert sp.drain() == []                      # ttl<=0 => no drain (matches run())
