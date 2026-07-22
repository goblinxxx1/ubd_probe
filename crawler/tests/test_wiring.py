from crawler.config import Config
from crawler.extract.base import CategoryIndex
from crawler.models import RawItem
from crawler.wiring import build_runner


def test_build_runner_wires_all_platforms():
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
    )
    runner = build_runner(cfg)
    assert set(runner._fetchers.keys()) == {"website", "telegram", "instagram", "facebook"}
    # extractor is the heuristic one (returns None on non-offer text)
    assert runner._extractor.extract(RawItem(1, "website", "k", ""), "P",
                                     CategoryIndex([], [])) is None


from crawler.discovery.query_grid import QueryGrid
from crawler.discovery.search_state import SearchState


def test_build_runner_rotates_query_grid_and_unions_pins(tmp_path):
    state_path = str(tmp_path / "state.json")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=True, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        search_providers=[],                 # provider None -> no network at build
        search_keywords=["мій пін"],
        search_state_path=state_path,
        search_queries_per_pass=3,
    )
    runner = build_runner(cfg)

    expected_batch, expected_cursor = QueryGrid().next_batch(3, 0)
    assert runner._keywords == expected_batch + ["мій пін"]
    assert SearchState.load(state_path).grid_cursor == expected_cursor
