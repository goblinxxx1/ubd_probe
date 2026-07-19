from crawler.extract.base import CategoryIndex
from crawler.extract.categories import resolve_offer_categories


class _FakeApi:
    def __init__(self, next_id=100):
        self.created = []
        self._next = next_id

    def create_offer_category(self, name, slug):
        self.created.append((name, slug))
        row = {"id": self._next, "name": name, "slug": slug}
        self._next += 1
        return row


def test_empty_matches_touches_nothing():
    api = _FakeApi()
    assert resolve_offer_categories(api, None, []) == []
    assert api.created == []


def test_existing_slug_reuses_id_without_create():
    api = _FakeApi()
    cats = CategoryIndex(offer=[{"id": 20, "name": "Кафе/ресторани", "slug": "food"}])
    ids = resolve_offer_categories(api, cats, [("Кафе/ресторани", "food")])
    assert ids == [20]
    assert api.created == []


def test_missing_slug_creates_once_and_caches():
    api = _FakeApi(next_id=100)
    cats = CategoryIndex(offer=[])
    ids1 = resolve_offer_categories(api, cats, [("Автосервіс", "auto")])
    ids2 = resolve_offer_categories(api, cats, [("Автосервіс", "auto")])
    assert ids1 == [100] and ids2 == [100]
    assert api.created == [("Автосервіс", "auto")]          # created exactly once
    assert {c["slug"] for c in cats.offer} == {"auto"}


def test_mixed_existing_and_new():
    api = _FakeApi(next_id=200)
    cats = CategoryIndex(offer=[{"id": 20, "name": "Кафе/ресторани", "slug": "food"}])
    ids = resolve_offer_categories(
        api, cats, [("Кафе/ресторани", "food"), ("Квіти", "flowers")])
    assert ids == [20, 200]
    assert api.created == [("Квіти", "flowers")]
