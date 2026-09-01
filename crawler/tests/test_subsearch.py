from dataclasses import dataclass, field
from crawler.discovery.subsearch import extract_business


@dataclass
class _Item:
    url: str | None = None
    text: str = ""
    locality: str | None = None
    links: list = field(default_factory=list)


@dataclass
class _Cand:
    url_or_handle: str
    type: str = "website"
    name: str | None = None


_URL = ("https://myhelp.com.ua/places/vinnytsia-language-school/services/"
        "znyzhka-dlia-uchasnykiv-boiovykh-dii")


def test_extract_business_name_from_url_slug():
    name, city = extract_business([_Item(url=_URL, locality="Вінниця")], _Cand(_URL))
    assert name == "vinnytsia language school"
    assert city == "Вінниця"


def test_extract_business_city_none_when_no_locality():
    name, city = extract_business([_Item(url=_URL)], _Cand(_URL))
    assert name == "vinnytsia language school"
    assert city is None


def test_extract_business_name_none_when_no_listing_segment():
    name, city = extract_business([_Item(url="https://x.ua/about")], _Cand("https://x.ua/about"))
    assert name is None


from dataclasses import dataclass
from crawler.discovery.subsearch import resolve_business_site


@dataclass
class _SC:
    url_or_handle: str
    type: str = "website"
    name: str | None = None


def _search_returning(*hosts):
    return lambda kw: [_SC(f"https://{h}/") for h in hosts]


def test_resolve_picks_first_clean_business_host():
    search = _search_returning("facebook.com", "vinnytsia-language-school.com.ua")
    # facebook — блокований/соціальний хост → пропущений; перемагає бізнес-хост
    host = resolve_business_site("vinnytsia language school", "Вінниця", search)
    assert host == "vinnytsia-language-school.com.ua"


def test_resolve_none_when_only_aggregators_and_social():
    search = _search_returning("facebook.com", "myhelp.com.ua")
    assert resolve_business_site("vinnytsia language school", "Вінниця", search) is None


def test_resolve_r1_generic_name_without_city_returns_none():
    search = _search_returning("planetfitness.com")
    # ≤2 токени ("планета фітнес") + city=None → відмова гадати (ризик омонімів)
    assert resolve_business_site("планета фітнес", None, search) is None


def test_resolve_r1_generic_name_with_city_allowed():
    search = _search_returning("planet-fitness-vinnytsia.com.ua")
    host = resolve_business_site("планета фітнес", "Вінниця", search)
    assert host == "planet-fitness-vinnytsia.com.ua"


def test_resolve_returns_none_when_search_raises():
    # пошук піднімає виключення → обробник ловить, повертає None
    def search(kw):
        raise RuntimeError("network down")
    # довга унікальна назва + місто щоб R1 не скоротив-схемив до пошуку
    assert resolve_business_site("vinnytsia language school", "Вінниця", search) is None


from crawler.discovery.subsearch import SubSearch


class _FakeHarvester:
    def __init__(self): self.crawled = []
    def harvest(self, candidates, cats, known, summary, known_hosts=None):
        self.crawled += [c.url_or_handle for c in candidates]
        return summary


def test_subsearch_resolves_and_crawls_via_isolated_harvester():
    search = _search_returning("vinnytsia-language-school.com.ua")
    hv = _FakeHarvester()
    ss = SubSearch(search, hv)
    summary = {"offers": 0, "errors": 0}
    ss.run([("vinnytsia language school", "Вінниця")], cats=None, known=set(),
           summary=summary, budget=15)
    assert hv.crawled == ["https://vinnytsia-language-school.com.ua"]


def test_subsearch_dedupes_same_name_within_pass():
    search = _search_returning("biz.com.ua")
    hv = _FakeHarvester()
    ss = SubSearch(search, hv)
    ss.run([("some unique business name", None), ("some unique business name", None)],
           cats=None, known=set(), summary={"offers": 0, "errors": 0}, budget=15)
    assert len(hv.crawled) == 1


def test_subsearch_budget_caps_number_of_searches():
    calls = {"n": 0}
    def search(kw):
        calls["n"] += 1
        return [_SC("https://biz-" + str(calls["n"]) + ".com.ua")]
    hv = _FakeHarvester()
    SubSearch(search, hv).run(
        [(f"unique business number {i}", None) for i in range(10)],
        cats=None, known=set(), summary={"offers": 0, "errors": 0}, budget=3)
    assert calls["n"] == 3


def test_subsearch_isolates_per_item_failure():
    def search(kw):
        raise RuntimeError("network down")
    hv = _FakeHarvester()
    # must not raise
    SubSearch(search, hv).run([("unique business name here", "Київ")],
                              cats=None, known=set(), summary={"offers": 0, "errors": 0},
                              budget=15)
    assert hv.crawled == []


def test_subsearch_run_isolates_harvester_failure():
    """Перевіряє, що harvest() виключення НЕ розповсюджується."""
    search = _search_returning("biz-a.com.ua")   # resolves fine

    class _RaisingThenOk:
        def __init__(self):
            self.calls = 0
        def harvest(self, candidates, cats, known, summary, known_hosts=None):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("harvest boom")
            return summary

    hv = _RaisingThenOk()
    ss = SubSearch(search, hv)
    # two DIFFERENT business names so both reach resolve+harvest
    ss.run([("business alpha name", "Київ"), ("business beta name", "Львів")],
           cats=None, known=set(), summary={"offers": 0, "errors": 0}, budget=15)
    assert hv.calls == 2      # first raised but was caught; second still attempted
