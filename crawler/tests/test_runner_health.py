from crawler.discovery.search_state import SearchState
from crawler.runner import Runner


class _Api:
    def __init__(self):
        self.posted = None

    def report_crawler_health(self, snap):
        self.posted = snap


class _BoomApi:
    def report_crawler_health(self, snap):
        raise RuntimeError("backend down")


class _Cfg:
    def __init__(self, path, active=True):
        self.active_discovery = active
        self.search_state_path = path
        self.search_backends = ["startpage", "duckduckgo", "yahoo", "brave"]


def _seed_state(path):
    st = SearchState(path)
    st.record_success("brave")     # persists the file
    return st


def test_report_health_tick_posts_snapshot(tmp_path):
    path = str(tmp_path / "s.json")
    _seed_state(path)
    api = _Api()
    r = Runner(api, {}, extractor=None, rate_limiter=None)
    r.report_health_tick(_Cfg(path))
    assert api.posted is not None
    assert [b["name"] for b in api.posted["backends"]] == \
        ["startpage", "duckduckgo", "yahoo", "brave"]
    assert "phrases" in api.posted


def test_report_health_tick_is_best_effort(tmp_path):
    path = str(tmp_path / "s.json")
    _seed_state(path)
    r = Runner(_BoomApi(), {}, extractor=None, rate_limiter=None)
    r.report_health_tick(_Cfg(path))          # must not raise


def test_report_health_tick_skipped_when_discovery_off(tmp_path):
    path = str(tmp_path / "s.json")
    _seed_state(path)
    api = _Api()
    r = Runner(api, {}, extractor=None, rate_limiter=None)
    r.report_health_tick(_Cfg(path, active=False))
    assert api.posted is None                  # no report when active_discovery is off
