from crawler.runner import Runner


def _src(i, type="website"):
    return {"id": i, "type": type, "name": f"S{i}", "url_or_handle": f"https://s{i}.example"}


class FakeApi:
    def __init__(self, uncrawled):
        self._uncrawled = list(uncrawled)
        self.uncrawled_limit = None
        self.uncrawled_called = False
        self.set_crawl_state_calls = []
    def list_uncrawled_sources(self, limit):
        self.uncrawled_called = True
        self.uncrawled_limit = limit
        return list(self._uncrawled)
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True): return []
    def set_crawl_state(self, source_id, last_seen_key):
        self.set_crawl_state_calls.append((source_id, last_seen_key)); return {}


class _Harv:
    def harvest(self, *a, **k): return 0


class _RecordingRunner(Runner):
    """Overrides the real deep-walk with a recorder so run_first_crawl orchestration is
    tested in isolation from the walker/fetcher machinery."""
    def __init__(self, *a, fail_ids=(), **k):
        super().__init__(*a, **k)
        self.crawled = []
        self._fail_ids = set(fail_ids)
    def _crawl_source(self, source, cats, known, summary):
        self.crawled.append(source["id"])
        if source["id"] in self._fail_ids:
            raise RuntimeError("boom")
        summary["offers"] += 1


def test_first_crawl_crawls_up_to_budget():
    api = FakeApi([_src(1), _src(2)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv())
    s = r.run_first_crawl(5)
    assert r.crawled == [1, 2]
    assert api.uncrawled_limit == 5
    assert s["offers"] == 2 and s["sources"] == 2


def test_first_crawl_marks_attempted_on_failure_and_isolates():
    api = FakeApi([_src(1), _src(2), _src(3)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv(), fail_ids={2})
    s = r.run_first_crawl(5)
    assert r.crawled == [1, 2, 3]                     # all attempted; #2 failure isolated
    assert api.set_crawl_state_calls == [(2, None)]   # only the failed one marked attempted
    assert s["errors"] == 1 and s["offers"] == 2


def test_first_crawl_budget_zero_is_noop():
    api = FakeApi([_src(1)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv())
    assert r.run_first_crawl(0) == r._empty_summary()
    assert r.crawled == [] and api.uncrawled_called is False


def test_first_crawl_empty_list_is_noop():
    api = FakeApi([])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv())
    s = r.run_first_crawl(5)
    assert r.crawled == [] and s == r._empty_summary()
    assert api.uncrawled_called is True


def test_run_active_runs_first_crawl_in_both_ddg_modes():
    for ddg in (True, False):
        api = FakeApi([_src(1)])
        r = _RecordingRunner(api, {}, None, None, harvester=_Harv(), first_crawl_budget=5)
        r.run_active(ddg_allowed=ddg)
        assert r.crawled == [1]


def test_run_active_skips_first_crawl_when_budget_zero():
    api = FakeApi([_src(1)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv(), first_crawl_budget=0)
    r.run_active(ddg_allowed=True)
    assert r.crawled == [] and api.uncrawled_called is False


def test_run_active_first_crawls_before_harvest():
    """First-crawl must run BEFORE discovery/harvest, else a heavy harvest starves it."""
    from crawler.models import SourceCandidate

    order = []

    class _OrderHarv:
        def harvest(self, candidates, cats, known, summary, known_hosts=None):
            order.append("harvest"); return 0

    class _Feed:  # a search_pass yielding one candidate so harvest is reached
        def run(self, known):
            return [SourceCandidate(name="c", type="website",
                                    url_or_handle="https://c.example")]
        def drain(self):
            return []

    class _OrderRunner(_RecordingRunner):
        def _crawl_source(self, source, cats, known, summary):
            order.append("first_crawl")
            super()._crawl_source(source, cats, known, summary)

    api = FakeApi([_src(1)])
    r = _OrderRunner(api, {}, None, None, harvester=_OrderHarv(),
                     search_pass=_Feed(), first_crawl_budget=5)
    r.run_active(ddg_allowed=True)
    assert order and order[0] == "first_crawl"   # first-crawl runs before harvest
    assert "harvest" in order                    # harvest still runs (not starved out)
