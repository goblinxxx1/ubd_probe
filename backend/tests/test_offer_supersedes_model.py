from app.crud import offer as offer_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def test_supersedes_link_roundtrips(db_session):
    parent = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                     OfferStatus.published, content_hash="p")
    child = Offer(type="discount", title="C", description="", provider="P",
                  status=OfferStatus.pending_review, created_by=CreatedBy.crawler,
                  supersedes_offer_id=parent.id)
    db_session.add(child)
    db_session.commit()
    db_session.refresh(child)
    assert child.supersedes_offer_id == parent.id
    assert child.supersedes.id == parent.id
