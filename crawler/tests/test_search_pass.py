from crawler.discovery.search_pass import SearchPass
from crawler.discovery.search_state import SearchState
from crawler.discovery.query_grid import QueryGrid
from crawler.models import SourceCandidate


class _Disc:
    """Fake ActiveDiscovery: records keyword lists, returns one candidate."""
    def __init__(self): self.calls = []
    def run(self, keywords, known, pages=None):
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
    def is_fresh(self, keyword, ttl_seconds, page=1):
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
    def is_fresh(self, kw, ttl, page=1): return False
    def set_grid_cursor(self, v): self.grid_cursor = v
    def current_page(self, phrase): return 1
    def record_page_result(self, phrase, page, new_count, page_cap): pass
    def record_yield(self, phrase, new_count, alpha=0.3): pass
    def effective_ttl(self, phrase, base_ttl, *, cold_tries=3, mult_cap=8.0): return base_ttl
    def note_host(self, host): pass
    @staticmethod
    def _key(keyword, page=1):
        base = keyword.strip().casefold()
        return base if int(page) <= 1 else f"{base}#p{int(page)}"


class _MultiDisc:
    def __init__(self, cands): self._c = cands
    def run(self, keywords, known, pages=None): return list(self._c)


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


class _PagedDisc:
    """Fake discovery whose new-candidate yield depends on the SERP page requested."""
    def __init__(self, phrase, yield_by_page):
        self.phrase = phrase
        self._yield = yield_by_page
        self.pages_seen = []
    def run(self, keywords, known, pages=None):
        page = (pages or {}).get(self.phrase, 1)
        self.pages_seen.append(page)
        n = self._yield.get(page, 0)
        return [SourceCandidate(name=f"c{i}", type="website",
                                url_or_handle=f"https://{self.phrase}-p{page}-{i}.ua",
                                discovery_note=f"x: {self.phrase}") for i in range(n)]


def _paged_plan(disc):
    from crawler.discovery.providers import SearchProviderPlan
    return SearchProviderPlan(name="x", discovery=disc, include_pins=False,
                              succeeded=(lambda: True), available=(lambda: True))


def test_pagination_climbs_then_stops_after_two_dry(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    disc = _PagedDisc("стоматологія", {1: 2, 2: 0, 3: 0})   # p1 productive, p2/p3 dry
    sp = SearchPass([_paged_plan(disc)], st, QueryGrid(["стоматологія"]),
                    block_size=1, ttl_seconds=1000.0, page_cap=3)
    sp.run(set()); assert st.current_page("стоматологія") == 2   # p1 productive → page 2
    sp.run(set()); assert st.current_page("стоматологія") == 3   # p2 dry #1 → probe page 3
    sp.run(set()); assert st.current_page("стоматологія") == 1   # p3 dry #2 → stop, reset
    assert disc.pages_seen == [1, 2, 3]                          # went one past the first empty


def test_pagination_stamps_page_into_origin_key(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    disc = _PagedDisc("готель", {1: 1, 2: 1})
    sp = SearchPass([_paged_plan(disc)], st, QueryGrid(["готель"]),
                    block_size=1, ttl_seconds=1000.0, page_cap=3)
    out1 = sp.run(set())
    assert out1[0].origin_key == "готель"          # page 1 → bare key (harvest-marking exact)
    out2 = sp.run(set())
    assert out2[0].origin_key == "готель#p2"        # page 2 → suffixed key


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


class _YieldPlan:
    """Fake plan matching the real SearchProviderPlan surface (discovery.run + succeeded/
    available), used to verify record_yield/note_host wiring and adaptive TTL end-to-end."""
    include_pins = False
    def __init__(self, results_by_kw):
        self._by = results_by_kw
        self._ok = True
    def available(self):
        return True
    def succeeded(self):
        return self._ok
    class _Disc:
        pass
    @property
    def discovery(self):
        d = _YieldPlan._Disc()
        d.run = self._run
        return d
    def _run(self, keywords, known, pages):
        # return the canned candidates whose phrase is in this batch
        out = []
        for kw in keywords:
            for c in self._by.get(kw, []):
                c.discovery_note = f"ddg: {kw}"
                out.append(c)
        return out


def _yield_cand(name, url):
    return SourceCandidate(name=name, type="website", url_or_handle=url,
                           discovered_from_source_id=None)


def test_dry_phrase_gets_longer_effective_ttl_and_is_skipped(tmp_path):
    # grid of two phrases; phrase A always dry, phrase B productive.
    grid = QueryGrid(["A", "B"])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    plan = _YieldPlan({"B": [_yield_cand("shopB", "https://b.ua")]})   # A yields nothing
    sp = SearchPass([plan], state, grid, block_size=2, ttl_seconds=100.0,
                    page_cap=1)
    # run several passes; advance clock a little each time (< base ttl)
    for _ in range(6):
        clock[0] += 10.0
        sp.run(known=set())
    # A drifted to a longer effective TTL (dry backoff); B stays base.
    assert state.effective_ttl("A", 100.0, cold_tries=3) > 100.0
    assert state.effective_ttl("B", 100.0, cold_tries=3) == 100.0
    # host_freq recorded B's domain at least once
    assert "b.ua" in state._data["host_freq"]


def test_productive_phrase_breeds_terms_low_yield_does_not(tmp_path):
    """Задача 5B: продуктивна фраза (>=promote_min нових кандидатів) розсіює
    сервіс-терми зі своїх кандидат-назв у breed_sink; бідна на урожай фраза — ні."""
    grid = QueryGrid(["стоматологія військовим", "квіти прикордонникам"])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    plan = _YieldPlan({"стоматологія військовим": [
        _yield_cand("Стоматологія Люкс Дніпро", "https://lux.ua"),
        _yield_cand("Стоматклініка Світ", "https://svit.ua")]})   # 2 new -> >= promote_min
    bred = []
    sp = SearchPass([plan], state, grid, block_size=2, ttl_seconds=100.0,
                    page_cap=1, breed_sink=bred.append, promote_min=2)
    clock[0] += 10.0
    sp.run(known=set())
    assert any("стоматолог" in t for t in bred)     # bred from the winning names
    # the barren phrase produced nothing -> no breeding from it
    assert all("квіт" not in t for t in bred)


def test_protected_phrase_never_retired(tmp_path):
    grid = QueryGrid(["ручний термін"])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    # make it look chronically dry
    for _ in range(10):
        state.record_yield("ручний термін", 0)
    sp = SearchPass([], state, grid, block_size=1, ttl_seconds=100.0,
                    protected_terms=frozenset({"ручний термін"}))
    # protected => due-walk uses base TTL, not the backed-off one
    assert sp._effective_ttl_for("ручний термін") == 100.0


def test_protected_service_term_exempts_composed_grid_phrase(tmp_path):
    """Регресія: adminʼ захищає БАЗОВИЙ сервіс-терм ("евакуатор"), але в _collect_due
    `kw` — це СКЛАДЕНА grid-фраза ("евакуатор знижка військовим"), бо build_grid
    завжди клеїть "{service} {modifier} {audience}"/"{service} {audience}". Точний
    membership-чек ("евакуатор" in protected_terms) НІКОЛИ не спрацює на композиті —
    людський override мовчки не діяв. Префіксний match має рятувати саме цей кейс."""
    composed = "евакуатор знижка військовим"
    grid = QueryGrid([composed])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    for _ in range(10):
        state.record_yield(composed, 0)          # хронічно суха складена фраза
    sp = SearchPass([], state, grid, block_size=1, ttl_seconds=100.0,
                    protected_terms=frozenset({"евакуатор"}))
    assert sp._effective_ttl_for(composed) == 100.0    # має бути base TTL, не backed-off


def test_non_protected_composed_phrase_still_backs_off(tmp_path):
    """Контрольний випадок: складена фраза, чий провідний сервіс-терм НЕ захищений,
    має продовжувати звичайний adaptive backoff (не отримує override за помилкою)."""
    composed = "шиномонтаж знижка військовим"
    grid = QueryGrid([composed])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    for _ in range(10):
        state.record_yield(composed, 0)
    sp = SearchPass([], state, grid, block_size=1, ttl_seconds=100.0,
                    protected_terms=frozenset({"евакуатор"}))
    assert sp._effective_ttl_for(composed) > 100.0    # не захищена -> звичайний backoff


def test_protected_service_term_exempts_real_build_grid_phrase(tmp_path):
    """Кінець-в-кінець(ish): реальний build_grid зі SEED_SERVICES дає складені фрази
    виду "{service} {modifier} {audience}"/"{service} {audience}"; захист базового
    сервіс-терму мусить звільняти принаймні одну з них від backoff."""
    from crawler.discovery.query_grid import build_grid, SERVICE_AUDIENCES
    service = "СТО"
    phrases = build_grid(cities=[], services=[service])
    composed = [p for p in phrases if p.casefold().startswith(service.casefold() + " ")]
    assert composed, "build_grid мав скласти хоч одну фразу з базовим сервіс-термом"
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    for p in composed:
        for _ in range(10):
            state.record_yield(p, 0)
    grid = QueryGrid(composed)
    sp = SearchPass([], state, grid, block_size=1, ttl_seconds=100.0,
                    protected_terms=frozenset({service}))
    for p in composed:
        assert sp._effective_ttl_for(p) == 100.0


def test_set_protected_terms_updates_live_without_rebuild(tmp_path):
    """Задача 5C: адмін захищає термін ПІД ЧАС роботи краулера (без рестарту) —
    set_protected_terms підмінює множину так само, як set_grid підмінює грід."""
    grid = QueryGrid(["новий термін"])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    for _ in range(10):
        state.record_yield("новий термін", 0)
    sp = SearchPass([], state, grid, block_size=1, ttl_seconds=100.0)
    assert sp._effective_ttl_for("новий термін") > 100.0     # dry-backed-off before protect
    sp.set_protected_terms(frozenset({"новий термін"}))
    assert sp._effective_ttl_for("новий термін") == 100.0    # base TTL right after the tick
