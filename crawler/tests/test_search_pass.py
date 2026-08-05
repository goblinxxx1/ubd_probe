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
