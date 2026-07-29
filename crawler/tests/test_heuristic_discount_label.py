from crawler.extract.base import CategoryIndex
from crawler.extract.heuristic import HeuristicExtractor
from crawler.models import RawItem


def _cats():
    return CategoryIndex(target=[{"id": 1, "slug": "ubd", "name": "УБД"}], offer=[])


def test_extract_sets_single_discount_with_snippet_label():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Військовим знижка 15% на все меню.", url="https://ex.com/p")
    cand = ex.extract(item, "Кафе", _cats())
    assert cand is not None
    assert len(cand.discounts) == 1
    d = cand.discounts[0]
    assert d["discount_type"] == "percent"
    assert d["discount_value"] == "15"
    assert d["label"] and "15%" in d["label"]
