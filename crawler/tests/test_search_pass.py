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
    def __init__(self, include_pins, ok, up=True):
        self.discovery = _Disc(); self.include_pins = include_pins; self._ok = ok
        self._up = up
    def succeeded(self): return self._ok
    def available(self): return self._up


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


class _Grid:
    def __init__(self, phrases): self._p = phrases
    def __len__(self): return len(self._p)
    def at(self, i): return self._p[i % len(self._p)]
    def next_batch(self, bs, cursor): return (self._p[:bs], (cursor + bs) % len(self._p))


class _State:
    def __init__(self): self.grid_cursor = 0
    def unharvested(self, ttl): return []
    def is_fresh(self, kw, ttl): return False
    def set_grid_cursor(self, v): self.grid_cursor = v


class _MultiDisc:
    def __init__(self, cands): self._c = cands
    def run(self, keywords, known): return list(self._c)


def _multi_plan(name, cands, available=True, succeeded=True):
    from crawler.discovery.providers import SearchProviderPlan
    return SearchProviderPlan(name=name, discovery=_MultiDisc(cands), include_pins=False,
                              succeeded=(lambda: succeeded), available=(lambda: available))


def _cand(url):
    return SourceCandidate(name="x", type="website", url_or_handle=url,
                           discovered_from_source_id=None, discovery_note=f"searxng: {url}")


def test_run_iterates_all_available_plans():
    ddg = _multi_plan("duckduckgo", [_cand("https://a.ua/1")], available=False)  # DDG backed off
    sx = _multi_plan("searxng", [_cand("https://b.ua/2")], available=True)
    sp = SearchPass([ddg, sx], _State(), _Grid(["знижка"]), block_size=1, ttl_seconds=0.0)
    out = sp.run(known=set())
    urls = {c.url_or_handle for c in out}
    assert urls == {"https://b.ua/2"}          # only the available (searxng) plan ran
    assert sp.any_provider_available() is True


def test_site_query_provider_prefers_available():
    ddg = _multi_plan("duckduckgo", [], available=False)
    sx = _multi_plan("searxng", [], available=True)
    sp = SearchPass([ddg, sx], _State(), _Grid(["x"]), block_size=1, ttl_seconds=0.0)
    assert sp.provider_for_site_query() is sx.discovery   # DDG down → site: routes via searxng


def test_no_provider_available():
    ddg = _multi_plan("duckduckgo", [], available=False)
    sx = _multi_plan("searxng", [], available=False)
    sp = SearchPass([ddg, sx], _State(), _Grid(["x"]), block_size=1, ttl_seconds=0.0)
    assert sp.any_provider_available() is False
    assert sp.provider_for_site_query() is None
