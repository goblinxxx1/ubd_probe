import json
import types

from crawler.judge.gate import RelevanceGate
from crawler.runner import Runner


def test_submit_query_candidates_posts_file(tmp_path):
    p = tmp_path / "cand.json"
    p.write_text(json.dumps([{"term": "імплантація", "z": 1.1, "support": 3},
                             {"term": ""}]), encoding="utf-8")

    class _Api:
        def __init__(self): self.posted = []
        def submit_query_candidates(self, items): self.posted.append(items)

    api = _Api()
    r = Runner(api, {}, object(), None)
    r._submit_query_candidates(types.SimpleNamespace(query_candidates_path=str(p)))
    assert api.posted == [[{"term": "імплантація", "z": 1.1, "support": 3}]]  # empty term dropped


def test_refresh_grid_from_approved_flows_terms(monkeypatch):
    import crawler.wiring as wiring
    from crawler.discovery import query_lexicon

    monkeypatch.setattr(wiring, "build_query_grid", lambda cfg: ["GRID"])

    class _SP:
        def __init__(self): self.grids = []
        def set_grid(self, g): self.grids.append(g)

    class _Api:
        def list_approved_query_terms(self): return ["імплантація"]

    sp = _SP()
    query_lexicon.reload_backend_terms(None)
    r = Runner(_Api(), {}, object(), None, search_pass=sp)
    r.refresh_grid_from_approved(config=object())
    assert "імплантація" in query_lexicon.compose_service_terms(seed=[], cap=0)
    assert sp.grids == [["GRID"]]
    query_lexicon.reload_backend_terms(None)


def test_refresh_noop_without_search_pass():
    class _Api:
        def list_approved_query_terms(self): raise AssertionError("must not be called")
    Runner(_Api(), {}, object(), None).refresh_grid_from_approved(config=object())  # no search_pass -> no-op


def test_refresh_grid_from_approved_also_flows_protected_terms(monkeypatch):
    """Задача 5C: той самий ~6h tick тягне ще й protected-терми в живий search_pass,
    без рестарту краулера — людський override діє одразу."""
    import crawler.wiring as wiring

    monkeypatch.setattr(wiring, "build_query_grid", lambda cfg: ["GRID"])

    class _SP:
        def __init__(self): self.protected = []
        def set_grid(self, g): pass
        def set_protected_terms(self, terms): self.protected.append(terms)

    class _Api:
        def list_approved_query_terms(self): return []
        def list_protected_query_terms(self): return ["ручний термін"]

    sp = _SP()
    r = Runner(_Api(), {}, object(), None, search_pass=sp)
    r.refresh_grid_from_approved(config=object())
    assert sp.protected == [frozenset({"ручний термін"})]


def test_refresh_protected_terms_fetch_best_effort(monkeypatch):
    """Мережа впала при фетчі protected — refresh не падає, грід все одно рефрешиться."""
    import crawler.wiring as wiring
    monkeypatch.setattr(wiring, "build_query_grid", lambda cfg: ["GRID"])

    class _SP:
        def __init__(self): self.grids = []
        def set_grid(self, g): self.grids.append(g)
        def set_protected_terms(self, terms): raise AssertionError("must not be reached")

    class _Api:
        def list_approved_query_terms(self): return []
        def list_protected_query_terms(self): raise RuntimeError("net down")

    sp = _SP()
    r = Runner(_Api(), {}, object(), None, search_pass=sp)
    r.refresh_grid_from_approved(config=object())   # must not raise
    assert sp.grids == [["GRID"]]


def test_flush_bred_terms_merges_and_refilters_fresh_rejects(tmp_path):
    """Задача 5B: _flush_bred_terms мусить (1) домішати bred-терми до вже написаних
    bootstrap'ом кандидатів БЕЗ втрати наявних (merge, не overwrite), (2) відсіяти
    свіжовідхилений терм за допомогою list_rejected_query_terms() навіть якщо той
    прийшов у bred_terms ще ДО відхилення, і (3) не створювати дублікатів."""
    p = tmp_path / "cand.json"
    p.write_text(json.dumps([{"term": "стоматологія", "z": 2.0, "support": 5}]),
                 encoding="utf-8")

    class _Api:
        def list_rejected_query_terms(self): return ["казино"]

    r = Runner(_Api(), {}, object(), None, bred_terms={"манікюр", "казино"})
    r._flush_bred_terms(types.SimpleNamespace(query_candidates_path=str(p)))

    cands = json.loads(p.read_text(encoding="utf-8"))
    terms = [c["term"] for c in cands]

    assert "стоматологія" in terms  # bootstrap-кандидат вижив (merge, не overwrite)
    assert "манікюр" in terms       # звичайний bred-терм додано
    assert "казино" not in terms    # свіжовідхилений bred-терм виключено
    assert len(terms) == len(set(terms))  # без дублікатів
    assert r._bred_terms == set()   # множина очищена після флашу


def _patch_rejudge_sweep(monkeypatch, run_result=None, run_exc=None):
    """Підміняє RejudgeSweep у crawler.discovery.rejudge (модуль, звідки Runner
    її локально імпортує) фейком, що записує аргументи конструктора та або
    повертає run_result, або кидає run_exc."""
    import crawler.discovery.rejudge as rejudge_mod

    calls = []

    class _FakeSweep:
        def __init__(self, api, judge, cache, *, budget):
            calls.append({"api": api, "judge": judge, "cache": cache, "budget": budget})

        def run(self):
            if run_exc is not None:
                raise run_exc
            return run_result if run_result is not None else {
                "scanned": 0, "kept": 0, "rejected": 0, "skipped": 0}

    monkeypatch.setattr(rejudge_mod, "RejudgeSweep", _FakeSweep)
    return calls


def test_rejudge_tick_runs_sweep_with_shared_judge_and_cache_when_enabled(monkeypatch):
    calls = _patch_rejudge_sweep(
        monkeypatch, run_result={"scanned": 2, "kept": 1, "rejected": 1, "skipped": 0})

    class _Api:
        pass

    api = _Api()
    judge = object()
    cache = object()
    gate = RelevanceGate(judge, cache, enabled=True)
    r = Runner(api, {}, object(), None, relevance_gate=gate)
    config = types.SimpleNamespace(judge_enabled=True, rejudge_enabled=True, rejudge_budget=30)

    r.rejudge_tick(config)

    assert calls == [{"api": api, "judge": judge, "cache": cache, "budget": 30}]


def test_rejudge_tick_noop_when_rejudge_disabled(monkeypatch):
    calls = _patch_rejudge_sweep(monkeypatch)
    gate = RelevanceGate(object(), object(), enabled=True)
    r = Runner(object(), {}, object(), None, relevance_gate=gate)
    config = types.SimpleNamespace(judge_enabled=True, rejudge_enabled=False, rejudge_budget=30)

    r.rejudge_tick(config)

    assert calls == []


def test_rejudge_tick_noop_when_judge_disabled(monkeypatch):
    calls = _patch_rejudge_sweep(monkeypatch)
    gate = RelevanceGate(object(), object(), enabled=False)
    r = Runner(object(), {}, object(), None, relevance_gate=gate)
    config = types.SimpleNamespace(judge_enabled=False, rejudge_enabled=True, rejudge_budget=30)

    r.rejudge_tick(config)

    assert calls == []


def test_rejudge_tick_never_raises_on_sweep_failure(monkeypatch):
    _patch_rejudge_sweep(monkeypatch, run_exc=RuntimeError("суддя недоступний назавжди"))
    gate = RelevanceGate(object(), object(), enabled=True)
    r = Runner(object(), {}, object(), None, relevance_gate=gate)
    config = types.SimpleNamespace(judge_enabled=True, rejudge_enabled=True, rejudge_budget=30)

    r.rejudge_tick(config)   # must not raise
