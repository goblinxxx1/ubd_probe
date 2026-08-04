from crawler.discovery.search_pass import SearchPass
from crawler.discovery.search_state import SearchState
from crawler.discovery.query_grid import QueryGrid
from crawler.models import SourceCandidate
from crawler.discovery.city_axis import CityAxis


class _Disc:
    """Fake ActiveDiscovery: records keyword lists, returns one candidate."""
    def __init__(self): self.calls = []
    def run(self, keywords, known):
        self.calls.append(list(keywords))
        return [SourceCandidate(name="c", type="website", url_or_handle="https://c.example")]


class _Plan:
    def __init__(self, name, cursor_key, include_pins, ok):
        self.name = name; self.discovery = _Disc(); self.cursor_key = cursor_key
        self.include_pins = include_pins; self._ok = ok; self.reset_calls = 0
    def succeeded(self): return self._ok
    def reset(self): self.reset_calls += 1


def _grid(): return QueryGrid([f"q{i}" for i in range(10)])


def test_providers_get_adjacent_blocks_and_pins(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=True)
    sp = SearchPass([ddg, sx], st, _grid(), block_size=3, static_keywords=["пін"])
    sp.run(set())
    # cycle 0: DDG block 0 (q0..q2)+pin ; searxng block 1 (q3..q5), no pin
    assert ddg.discovery.calls == [["q0", "q1", "q2", "пін"]]
    assert sx.discovery.calls == [["q3", "q4", "q5"]]
    assert st.block_cursor == 6            # advanced N*block_size = 2*3


def test_blocks_swap_provider_next_cycle(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    grid = QueryGrid([f"q{i}" for i in range(6)])
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=True)
    sp = SearchPass([ddg, sx], st, grid, block_size=3)
    sp.run(set())                          # cycle 0: DDG q0-2, sx q3-5 ; cursor 6 -> wrap -> cycle 1
    assert st.cycle == 1 and st.block_cursor == 0
    sp.run(set())                          # cycle 1: swap -> DDG q3-5, sx q0-2
    assert ddg.discovery.calls[-1] == ["q3", "q4", "q5"]
    assert sx.discovery.calls[-1] == ["q0", "q1", "q2"]


def test_no_advance_when_all_providers_fail(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=False)
    sp = SearchPass([ddg], st, _grid(), block_size=3)
    sp.run(set())
    assert st.block_cursor == 0 and st.cycle == 0
    assert ddg.reset_calls == 1


def test_provider_for_site_query_prefers_ddg(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=True)
    sp = SearchPass([sx, ddg], st, _grid(), block_size=2)
    assert sp.provider_for_site_query() is ddg.discovery


def test_city_queries_merged_and_cursor_advances(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sp = SearchPass([ddg], st, _grid(), block_size=2, static_keywords=["пін"],
                    city_axis=CityAxis(["Львів", "Одеса"]), city_queries_per_pass=2)
    sp.run(set())
    # base q0,q1 + pin, then current city (Львів) suffixed onto the base phrases
    assert ddg.discovery.calls == [["q0", "q1", "пін", "q0 Львів", "q1 Львів"]]
    assert st.city_cursor == 1                    # advanced once: (0+1) % 2


def test_city_cursor_holds_when_all_providers_fail(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=False)
    sp = SearchPass([ddg], st, _grid(), block_size=2,
                    city_axis=CityAxis(["Львів", "Одеса"]), city_queries_per_pass=2)
    sp.run(set())
    assert st.city_cursor == 0                    # no advance on all-fail


def test_city_axis_absent_is_byte_equivalent(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sp = SearchPass([ddg], st, _grid(), block_size=2, static_keywords=["пін"])
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1", "пін"]]
    assert st.city_cursor == 0


def test_city_queries_per_pass_zero_is_off(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sp = SearchPass([ddg], st, _grid(), block_size=2,
                    city_axis=CityAxis(["Львів"]), city_queries_per_pass=0)
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1"]]
    assert st.city_cursor == 0
