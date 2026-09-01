from crawler.runner import Runner


class FakeApi:
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True): return []


class FakeHarvester:
    """Головний харвестер: тут нас цікавить лише take_directory_businesses()."""
    def __init__(self, directory_businesses=None):
        self._directory_businesses = list(directory_businesses or [])
        self.calls = []

    def harvest(self, candidates, cats, known, summary, known_hosts=None):
        self.calls.append(list(candidates))

    def take_directory_businesses(self):
        out = self._directory_businesses
        self._directory_businesses = []
        return out


class FakeSubSearch:
    def __init__(self):
        self.ran_with = None
        self.budget = None

    def run(self, businesses, cats, known, summary, budget):
        self.ran_with = list(businesses)
        self.budget = budget


def make_runner_with_subsearch(directory_businesses=None):
    api = FakeApi()
    main_hv = FakeHarvester(directory_businesses)
    subsearch = FakeSubSearch()
    r = Runner(api, {}, extractor=None, rate_limiter=None,
               harvester=main_hv, subsearch=subsearch,
               subsearch_search_budget=15)
    return r, main_hv, subsearch


def test_run_active_runs_subsearch_when_ddg_allowed():
    r, main_hv, subsearch = make_runner_with_subsearch()
    main_hv._directory_businesses = [("easy english", "Вінниця")]
    r.run_active(ddg_allowed=True)
    assert subsearch.ran_with == [("easy english", "Вінниця")]  # fake SubSearch records run()
    assert subsearch.budget == 15


def test_run_active_skips_subsearch_under_backoff():
    r, main_hv, subsearch = make_runner_with_subsearch()
    main_hv._directory_businesses = [("easy english", "Вінниця")]
    r.run_active(ddg_allowed=False)
    assert subsearch.ran_with is None                            # skipped under backoff
    assert main_hv._directory_businesses == []                   # but queue was drained


def test_run_active_skips_subsearch_when_no_directory_businesses():
    r, main_hv, subsearch = make_runner_with_subsearch()
    r.run_active(ddg_allowed=True)
    assert subsearch.ran_with is None                            # nothing to search


def test_run_active_drains_queue_when_no_subsearch_provider():
    """Verify queue is drained even when subsearch provider is None."""
    api = FakeApi()
    main_hv = FakeHarvester([("lang courses", "Київ")])
    r = Runner(api, {}, extractor=None, rate_limiter=None,
               harvester=main_hv, subsearch=None,  # no subsearch provider
               subsearch_search_budget=15)
    r.run_active(ddg_allowed=True)
    assert main_hv._directory_businesses == []                   # queue drained despite no provider
