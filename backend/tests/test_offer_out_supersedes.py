from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate, OfferOut
from app.schemas.source import SourceCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def test_offer_out_exposes_supersede_context(db_session):
    s = source_crud.create_source(
        db_session, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)
    p = offer_crud.create_offer(db_session, _offer(title="Parent", discount_value="10"),
                                CreatedBy.crawler, OfferStatus.published,
                                source_id=s.id, content_hash="h1")
    shadow = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                     OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    out = OfferOut.model_validate(shadow)
    assert out.supersedes_offer_id == p.id
    assert out.supersedes.id == p.id
    assert out.supersedes.title == "Parent"
    assert str(out.supersedes.discount_value) == "10.00"


def test_offer_out_supersedes_none_for_plain_offer(db_session):
    o = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h9")
    out = OfferOut.model_validate(o)
    assert out.supersedes_offer_id is None
    assert out.supersedes is None
