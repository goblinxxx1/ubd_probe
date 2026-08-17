from decimal import Decimal
from types import SimpleNamespace

from app.crud.dedup import (normalize_tokens, text_similarity,
                            discount_magnitudes, is_duplicate_promo)
from app.models.enums import DiscountType


def test_normalize_tokens_drops_stopwords_and_punctuation():
    toks = normalize_tokens("Знижка 15% для військових!")
    assert {"знижка", "15", "військових"} <= toks
    assert "для" not in toks


def test_normalize_tokens_empty():
    assert normalize_tokens("") == frozenset()
    assert normalize_tokens(None) == frozenset()


def test_text_similarity_identical_and_disjoint():
    a = normalize_tokens("знижка військовим на послуги")
    assert text_similarity(a, a) == 1.0
    b = normalize_tokens("безкоштовна кава студентам")
    assert text_similarity(a, b) == 0.0


def test_text_similarity_paraphrase_above_half():
    a = normalize_tokens("знижка 15% військовим на всі послуги клініки")
    b = normalize_tokens("військовим знижка 15% на послуги нашої клініки")
    assert text_similarity(a, b) > 0.6


def test_discount_magnitudes_multi_and_fallback():
    d1 = SimpleNamespace(discount_type=DiscountType.percent, discount_value=Decimal("30"))
    d2 = SimpleNamespace(discount_type=DiscountType.percent, discount_value=Decimal("50"))
    assert discount_magnitudes([d1, d2], None, None) == frozenset({
        (DiscountType.percent, Decimal("30")), (DiscountType.percent, Decimal("50"))})
    assert discount_magnitudes([], DiscountType.percent, Decimal("15")) == frozenset({
        (DiscountType.percent, Decimal("15"))})


def test_is_duplicate_promo_subset_similar_true():
    p = frozenset({(DiscountType.percent, Decimal("30"))})
    both = frozenset({(DiscountType.percent, Decimal("30")), (DiscountType.percent, Decimal("50"))})
    a = normalize_tokens("знижка 30% військовим на меблі")
    b = normalize_tokens("військовим 30% знижка на меблі магазину")
    assert is_duplicate_promo(a, p, b, both, 0.6) is True


def test_is_duplicate_promo_same_percent_different_text_false():
    p = frozenset({(DiscountType.percent, Decimal("10"))})
    a = normalize_tokens("знижка 10% військовим на меблі")
    c = normalize_tokens("знижка 10% студентам на каву")
    assert is_duplicate_promo(a, p, c, p, 0.6) is False


def test_is_duplicate_promo_superset_false():
    p = frozenset({(DiscountType.percent, Decimal("30"))})
    both = frozenset({(DiscountType.percent, Decimal("30")), (DiscountType.percent, Decimal("50"))})
    a = normalize_tokens("знижки військовим 30% та ветеранам 50%")
    b = normalize_tokens("військовим знижка 30% на все")
    # a offers extra 50% not in b -> not a duplicate of b
    assert is_duplicate_promo(a, both, b, p, 0.6) is False
