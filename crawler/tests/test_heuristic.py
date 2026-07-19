from crawler.extract.base import CategoryIndex, get_extractor
from crawler.models import RawItem


CATS = CategoryIndex(
    target=[{"id": 10, "name": "Ветеран", "slug": "veteran"}],
    offer=[{"id": 20, "name": "Кафе/ресторани", "slug": "food"}],
)


def _item(text):
    return RawItem(source_id=1, platform="website", key="k", text=text)


def test_non_offer_returns_none():
    ex = get_extractor("heuristic")
    assert ex.extract(_item("Просто новина без пропозицій"), "Shop", CATS) is None


def test_percent_discount_parsed():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Знижка 20% для ветеранів у нашому кафе"), "Кафе Львів", CATS)
    assert cand is not None
    assert cand.discount_type == "percent"
    assert cand.discount_value == "20"
    assert cand.provider == "Кафе Львів"
    assert 10 in cand.target_category_ids                       # "ветеран" → veteran
    assert ("Кафе/ресторани", "food") in cand.offer_category_matches   # "кафе" → food
    assert cand.offer_category_ids == []                        # ids filled later by resolver
    assert len(cand.content_hash) == 64


def test_free_offer_parsed():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Безкоштовно для військових!"), "Музей", CATS)
    assert cand is not None
    assert cand.discount_type == "free"
    assert cand.discount_value is None


def test_location_from_structured_locality():
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів у кафе", locality="Львів")
    cand = get_extractor("heuristic").extract(it, "Кафе", CATS)
    assert cand.location == "Львів"


def test_location_from_gazetteer_fallback():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів у нашому кафе в Одесі"), "Кафе", CATS)
    assert cand.location == "Одеса"


def test_location_none_when_absent():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів"), "Кафе", CATS)
    assert cand.location is None


def test_location_online_fallback():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів у нашому інтернет-магазині"), "Shop", CATS)
    assert cand.location == "Онлайн"


def test_title_is_concise_headline():
    text = ("Знижка 20% для ветеранів. Пропозиція діє у нашому кафе протягом "
            "усього місяця на всі напої та десерти без винятку сьогодні.")
    cand = get_extractor("heuristic").extract(_item(text), "Кафе", CATS)
    assert cand.title == "Знижка 20% для ветеранів."
    assert cand.body == text  # description keeps the full text


def test_local_llm_is_hook_only():
    import pytest
    with pytest.raises(NotImplementedError):
        get_extractor("local_llm")


def test_offer_category_from_site_name_context():
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів", site_name="Барбершоп Резервіст")
    cand = get_extractor("heuristic").extract(it, "Shop", CATS)
    assert ("Краса та догляд", "beauty") in cand.offer_category_matches


def test_target_from_military_keyword_resolves_existing_only():
    # "військових" → ubd, but CATS has no ubd row → no id resolved (no creation)
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для військових"), "Shop", CATS)
    assert cand.target_category_ids == []
