from crawler.discovery.harvest import ActiveHarvester
from crawler.extract.base import CategoryIndex
from crawler.models import RawItem, SourceCandidate


class _FakeApi:
    def __init__(self):
        self.offers = []
    def submit_offer(self, payload):
        self.offers.append(payload)
    def submit_suggestion(self, payload):
        pass


class _FakeFetcher:
    # two promo blocks from ONE page (same url), different discounts.
    # site_name + a first-person marker ("у нас") give attribute() a first-party
    # provider under the legacy (hardening_enabled=False) path for both blocks.
    def fetch(self, src, last_key):
        url = src["url_or_handle"]
        return ([RawItem(source_id=1, platform="website", key="a",
                         text="У нас військовим знижка 10% завжди.", url=url, links=[],
                         site_name="X"),
                 RawItem(source_id=1, platform="website", key="b",
                         text="У нас ветеранам знижка 15% на все.", url=url, links=[],
                         site_name="X")], last_key)


def test_active_harvest_submits_one_offer_per_page():
    from crawler.extract.heuristic import HeuristicExtractor
    api = _FakeApi()
    h = ActiveHarvester(api=api, fetchers={"website": _FakeFetcher()},
                        extractor=HeuristicExtractor(), rate_limiter=None,
                        hardening_enabled=False)
    cats = CategoryIndex(target=[{"id": 1, "slug": "ubd", "name": "УБД"},
                                  {"id": 2, "slug": "veteran", "name": "Ветеран"}], offer=[])
    cand = SourceCandidate(name="X", type="website", url_or_handle="https://ex.com/promo")
    summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}
    h.harvest([cand], cats, set(), summary)
    assert len(api.offers) == 1
    assert len(api.offers[0]["discounts"]) == 2
