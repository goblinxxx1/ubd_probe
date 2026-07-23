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


from crawler.discovery.walker import WalkPlan


class _Fetcher:
    """Records fetched URLs; returns one trivial passing item per page."""
    def __init__(self):
        self.urls = []

    def fetch(self, source, last_seen_key):
        self.urls.append(source["url_or_handle"])
        item = RawItem(source_id=None, platform="website", key="k",
                       text="Ми пропонуємо знижку 20% для ветеранів у нас",
                       url=source["url_or_handle"], links=[], site_name="Shop")
        return [item], None


class _Extractor:
    def extract(self, item, provider, cats):
        if provider == "":
            return object()   # passes the relevance gate
        from crawler.models import OfferCandidate
        return OfferCandidate(source_id=None, title="t", provider=provider, body="b")


class _Api:
    def __init__(self):
        self.offers = []

    def submit_offer(self, payload):
        self.offers.append(payload)

    def submit_suggestion(self, payload):
        pass


class _Walker:
    def __init__(self, urls):
        self._urls = urls

    def walk(self, cand):
        return WalkPlan(domain="shop.ua", urls=self._urls, crawl_delay=1.0)


class _DomainRL:
    def __init__(self):
        self.calls = []

    def wait(self, domain, delay=None):
        self.calls.append((domain, delay))


def _website_cand():
    return SourceCandidate(name="Shop", type="website", url_or_handle="https://shop.ua")


def test_walker_expands_website_candidate_to_multiple_pages(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx, **kw: type("A", (), {
                            "provider": "shop.ua", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Shop"})())
    fetcher = _Fetcher()
    drl = _DomainRL()
    harv = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=None,
                           walker=_Walker(["https://shop.ua", "https://shop.ua/sale"]),
                           domain_rate_limiter=drl)
    summary = {"offers": 0, "suggestions": 0, "errors": 0}
    harv.harvest([_website_cand()], cats=object(), known=set(), summary=summary)
    assert fetcher.urls == ["https://shop.ua", "https://shop.ua/sale"]
    assert drl.calls == [("shop.ua", 1.0), ("shop.ua", 1.0)]


def test_walker_none_keeps_single_homepage_fetch(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx, **kw: type("A", (), {
                            "provider": "shop.ua", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Shop"})())

    class PlatformRL:
        def __init__(self):
            self.calls = []

        def wait(self, platform):
            self.calls.append(platform)

    fetcher = _Fetcher()
    prl = PlatformRL()
    harv = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=prl)
    summary = {"offers": 0, "suggestions": 0, "errors": 0}
    harv.harvest([_website_cand()], cats=object(), known=set(), summary=summary)
    assert fetcher.urls == ["https://shop.ua"]     # single homepage fetch, unchanged
    assert prl.calls == ["website"]                 # per-platform wait, unchanged


def test_one_broken_page_does_not_stop_the_domain(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx, **kw: type("A", (), {
                            "provider": "shop.ua", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Shop"})())

    class FlakyFetcher(_Fetcher):
        def fetch(self, source, last_seen_key):
            if source["url_or_handle"].endswith("/boom"):
                raise RuntimeError("dead page")
            return super().fetch(source, last_seen_key)

    fetcher = FlakyFetcher()
    harv = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=None,
                           walker=_Walker(["https://shop.ua/boom", "https://shop.ua/sale"]),
                           domain_rate_limiter=_DomainRL())
    summary = {"offers": 0, "suggestions": 0, "errors": 0}
    harv.harvest([_website_cand()], cats=object(), known=set(), summary=summary)
    assert summary["errors"] == 1
    assert "https://shop.ua/sale" in fetcher.urls    # continued after the broken page


from crawler.discovery.domain_registry import DomainRegistry


class _RecFetcher:
    """One block; offer iff text has '%'."""
    def __init__(self, text): self._text = text
    def fetch(self, source, last_seen_key):
        return [RawItem(source_id=None, platform="website", key="k", text=self._text,
                        url=source["url_or_handle"], links=[], site_name="Cafe")], None


def test_website_candidate_in_known_hosts_is_skipped(tmp_path):
    api = FakeApi()
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        domain_registry=reg)
    summary = _summary()
    h.harvest([_cand(url="https://cafe.example")], cats=None, known=set(),
              summary=summary, known_hosts={"cafe.example"})
    assert api.offers == []                       # never fetched
    assert reg.score("cafe.example") == 0.0       # never recorded


def test_registry_records_offers_per_domain(tmp_path):
    api = FakeApi()
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0, offer_weight=1.0)
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        domain_registry=reg)
    summary = _summary()
    h.harvest([_cand(url="https://cafe.example")], cats=None, known=set(), summary=summary)
    assert summary["offers"] == 1
    assert reg.score("cafe.example") == 1.0       # 1 offer recorded


def test_registry_not_recorded_without_registry():
    # regression: existing 4-arg call still works (no known_hosts, no registry)
    api = FakeApi()
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand(url="https://cafe.example")], cats=None, known=set(), summary=summary)
    assert summary["offers"] == 1


def test_harvester_threads_aggregator_threshold(monkeypatch):
    import crawler.discovery.harvest as hv
    seen = {}
    def spy(item, ctx, **kw):
        seen.update(kw)
        return None                      # drop → no offer submitted
    monkeypatch.setattr(hv, "attribute", spy)
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([_item("Знижка 20% для УБД у нас",
                                                            site_name="Cafe")])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        aggregator_min_outbound=7)
    h.harvest([_cand()], cats=None, known=set(), summary=_summary())
    assert seen.get("aggregator_min_outbound") == 7


def test_source_candidate_defaults_no_bypass():
    assert SourceCandidate(name="x", type="website",
                           url_or_handle="https://x.ua").bypass_host_skip is False


def test_bypass_host_skip_forces_fetch_of_known_host(tmp_path):
    api = FakeApi()
    cand = _cand(url="https://cafe.example")
    cand.bypass_host_skip = True                       # site:-sourced candidate
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([cand], cats=None, known=set(), summary=summary,
              known_hosts={"cafe.example"})            # host normally skipped
    assert summary["offers"] == 1                      # fetched anyway
