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
