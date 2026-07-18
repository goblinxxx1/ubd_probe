from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate, RawItem, OfferCandidate


class FakeApi:
    def __init__(self):
        self.offers = []
        self.suggested = []
    def submit_offer(self, p): self.offers.append(p); return {}
    def submit_suggestion(self, p): self.suggested.append(p); return {}


class FakeFetcher:
    def __init__(self, items): self._items = items
    def fetch(self, source, last_seen_key): return list(self._items), None


class GateExtractor:
    """Returns an OfferCandidate for blocks whose text has '%', else None."""
    def extract(self, item, provider, cats):
        if "%" not in (item.text or ""):
            return None
        return OfferCandidate(source_id=item.source_id, title=item.text[:50],
                              provider=provider, body=item.text, content_hash="h")


def _cand(url="https://cafe.example", type="website", name="Cafe"):
    return SourceCandidate(name=name, type=type, url_or_handle=url)


def _item(text, site_name=None, links=None):
    return RawItem(source_id=None, platform="website", key="k", text=text,
                   url="https://cafe.example/page", links=links or [], site_name=site_name)


def _summary():
    return {"offers": 0, "suggestions": 0, "errors": 0}


def test_valid_first_party_offer_and_suggestion():
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([_item("Знижка 20% для УБД у нас",
                                                            site_name="Cafe")])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert len(api.offers) == 1 and api.offers[0]["provider"] == "Cafe"
    assert api.offers[0]["source_id"] is None
    assert len(api.suggested) == 1
    assert api.suggested[0]["url_or_handle"] == "https://cafe.example"
    assert summary["offers"] == 1 and summary["suggestions"] == 1


def test_generic_info_rejected():
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([_item("Для УБД існують знижки 10%")])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert api.offers == [] and api.suggested == []


def test_fetch_budget_caps_fetches():
    api = FakeApi()
    fetched = []
    class CountingFetcher:
        def fetch(self, source, k): fetched.append(source["url_or_handle"]); return [], None
    h = ActiveHarvester(api, {"website": CountingFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=2)
    cands = [_cand(url=f"https://s{i}.example") for i in range(5)]
    h.harvest(cands, cats=None, known=set(), summary=_summary())
    assert len(fetched) == 2


def test_known_candidate_skipped():
    api = FakeApi()
    fetched = []
    class CountingFetcher:
        def fetch(self, source, k): fetched.append(1); return [], None
    h = ActiveHarvester(api, {"website": CountingFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5)
    known = {normalize_ref("website", "https://cafe.example")}
    h.harvest([_cand()], cats=None, known=known, summary=_summary())
    assert fetched == []


def test_error_in_one_candidate_isolated():
    api = FakeApi()
    class BoomFetcher:
        def fetch(self, source, k): raise RuntimeError("boom")
    h = ActiveHarvester(api, {"website": BoomFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert summary["errors"] == 1 and api.offers == []
