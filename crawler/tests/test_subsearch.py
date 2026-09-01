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
