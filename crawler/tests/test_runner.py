from crawler.extract.base import get_extractor
from crawler.models import RawItem
from crawler.ratelimit import RateLimiter
from crawler.runner import Runner


class FakeFetcher:
    platform = "website"

    def __init__(self, items):
        self._items = items

    def fetch(self, source, last_seen_key):
        return self._items, "newkey"


class BoomFetcher:
    platform = "telegram"

    def fetch(self, source, last_seen_key):
        raise RuntimeError("boom")


class FakeApi:
    def __init__(self, sources):
        self._sources = sources
        self.offers = []
        self.suggestions = []
        self.state = {}
        self.created = []
        self._offer_cats = []

    def list_target_categories(self): return []
    def list_offer_categories(self): return list(self._offer_cats)
    def create_offer_category(self, name, slug):
        row = {"id": 900 + len(self.created), "name": name, "slug": slug}
        self.created.append((name, slug)); self._offer_cats.append(row)
        return row
    def list_sources(self, is_active=True): return self._sources
    def get_crawl_state(self, source_id): return {"last_seen_key": None, "last_crawled_at": None}
    def set_crawl_state(self, source_id, last_seen_key): self.state[source_id] = last_seen_key; return {}
    def submit_offer(self, payload): self.offers.append(payload); return {"id": len(self.offers)}
    def submit_suggestion(self, payload): self.suggestions.append(payload); return {"id": 1}


def _rl():
    return RateLimiter(min_delay=0, sleep=lambda s: None, monotonic=lambda: 0.0)


def test_runner_submits_offer_and_suggestion_and_state():
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів. Підпишись @newchan", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl())

    summary = runner.run()
    assert summary["offers"] == 1
    assert api.offers[0]["discount_type"] == "percent"
    assert api.offers[0]["content_hash"]
    assert summary["suggestions"] == 1
    assert api.state[1] == "newkey"
    assert summary["errors"] == 0


def test_runner_isolates_source_failure():
    good = {"id": 1, "type": "website", "name": "S1", "url_or_handle": "http://x"}
    bad = {"id": 2, "type": "telegram", "name": "S2", "url_or_handle": "@chan"}
    item = RawItem(source_id=1, platform="website", key="k", text="Акція 10%", links=[])
    api = FakeApi([bad, good])
    fetchers = {"website": FakeFetcher([item]), "telegram": BoomFetcher()}
    runner = Runner(api, fetchers, get_extractor("heuristic"), _rl())

    summary = runner.run()
    assert summary["errors"] == 1      # telegram source #2 failed
    assert summary["offers"] == 1      # website source #1 still processed


def test_runner_autocreates_offer_category():
    src = {"id": 1, "type": "website", "name": "Барбершоп", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів на стрижку у барбершопі", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl())

    runner.run()
    assert api.created == [("Краса та догляд", "beauty")]
    assert api.offers[0]["offer_category_ids"] == [900]
