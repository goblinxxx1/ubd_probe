from decimal import Decimal

from app.dedup_queue import find_duplicates
from app.models import Offer, OfferDiscount
from app.models.enums import CreatedBy, OfferStatus, DiscountType, OfferType


def _raw(db, article, host, desc, val="15", label="x"):
    o = Offer(type=OfferType.discount, title="T", description=desc, provider="P",
              discount_type=DiscountType.percent, discount_value=Decimal(val),
              site_url=f"https://{host}", article_url=f"https://{host}{article}",
              status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    o.discounts = [OfferDiscount(label=label, discount_type=DiscountType.percent,
                                 discount_value=Decimal(val), sort_order=0)]
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def test_find_duplicates_pairs_same_promo(db_session):
    a = _raw(db_session, "/aktsiyi", "x.com.ua", "Знижка 15% військовим на послуги")
    b = _raw(db_session, "/pro-nas", "x.com.ua", "Військовим знижка 15% на послуги")
    c = _raw(db_session, "/o", "y.com.ua", "Безкоштовна доставка усім клієнтам")  # different host
    pairs = find_duplicates(db_session, 0.6)
    assert (b.id, a.id) in pairs
    assert all(p[0] != c.id for p in pairs)


def test_find_duplicates_idempotent_after_reject(db_session):
    a = _raw(db_session, "/1", "z.com.ua", "Знижка 20% ветеранам на все")
    b = _raw(db_session, "/2", "z.com.ua", "Ветеранам знижка 20% на все")
    assert (b.id, a.id) in find_duplicates(db_session, 0.6)
    b.status = OfferStatus.rejected
    db_session.commit()
    assert find_duplicates(db_session, 0.6) == []
