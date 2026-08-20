import json
import types

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
