from decimal import Decimal

from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType
from app.schemas.offer import OfferCreate, OfferUpdate


def _seed(db):
    data = OfferCreate(type=OfferType.discount, title="T", provider="P",
                       discount_type=DiscountType.percent, discount_value=Decimal("10"),
                       article_url="https://ex.com/a")
    return offer_crud.create_offer(db, data, CreatedBy.admin, OfferStatus.published)


def test_update_replaces_discounts_and_recomputes_article_canonical(db_session):
    o = _seed(db_session)
    upd = OfferUpdate(article_url="https://www.ex.com/b",
                      discounts=[{"label": "Курсанти", "discount_type": "percent", "discount_value": 15},
                                 {"label": "ЗСУ", "discount_type": "free", "discount_value": None}])
    out = offer_crud.update_offer(db_session, o.id, upd)
    assert [d.label for d in out.discounts] == ["Курсанти", "ЗСУ"]
    assert out.article_url_canonical == "ex.com/b"  # www stripped
