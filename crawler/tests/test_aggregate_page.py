# crawler/tests/test_aggregate_page.py
from crawler.extract.aggregate import aggregate_page
from crawler.models import OfferCandidate


def _c(**kw):
    base = dict(source_id=1, title="Кафе на розі", provider="Кафе", body="b",
                article_url="https://ex.com/p", site_url="https://ex.com")
    base.update(kw)
    return OfferCandidate(**base)


def test_aggregate_unions_discounts_categories_and_picks_best_primary():
    a = _c(discount_type="percent", discount_value="10", target_category_ids=[1],
           offer_category_matches=[("Їжа", "food")],
           discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": "10"}])
    b = _c(discount_type="percent", discount_value="15", target_category_ids=[2],
           offer_category_matches=[("Кава", "coffee")],
           discounts=[{"label": "ЗСУ", "discount_type": "percent", "discount_value": "15"}])
    out = aggregate_page([a, b])
    assert out is not None
    assert len(out.discounts) == 2
    assert sorted(out.target_category_ids) == [1, 2]
    assert {s for _, s in out.offer_category_matches} == {"food", "coffee"}
    # primary = best (highest percent)
    assert out.discount_type == "percent" and out.discount_value == "15"


def test_aggregate_dedups_identical_discounts_and_hash_is_order_independent():
    a = _c(discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": "10"}],
           discount_type="percent", discount_value="10")
    b = _c(discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": "10"}],
           discount_type="percent", discount_value="10")
    out = aggregate_page([a, b])
    assert len(out.discounts) == 1
    # reversed input -> same content_hash (order-independent)
    assert aggregate_page([b, a]).content_hash == out.content_hash


def test_aggregate_empty_returns_none():
    assert aggregate_page([]) is None
