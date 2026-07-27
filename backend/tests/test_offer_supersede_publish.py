from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models import AdminUser
from app.models.enums import AdminRole, CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def _admin(db):
    a = AdminUser(email="m@example.com", password_hash="x", role=AdminRole.moderator)
    db.add(a); db.commit(); db.refresh(a)
    return a


def _setup_shadow(db):
    s = source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)
    p = offer_crud.create_offer(db, _offer(discount_value="10"), CreatedBy.crawler,
                                OfferStatus.published, source_id=s.id, content_hash="h1")
    shadow = offer_crud.create_offer(db, _offer(discount_value="20"), CreatedBy.crawler,
                                     OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    return p, shadow


def test_publish_shadow_expires_parent(db_session):
    p, shadow = _setup_shadow(db_session)
    admin = _admin(db_session)
    offer_crud.set_status(db_session, shadow.id, OfferStatus.published, admin.id)
    db_session.refresh(p); db_session.refresh(shadow)
    assert shadow.status == OfferStatus.published
    assert p.status == OfferStatus.expired


def test_reject_shadow_leaves_parent_published(db_session):
    p, shadow = _setup_shadow(db_session)
    admin = _admin(db_session)
    offer_crud.set_status(db_session, shadow.id, OfferStatus.rejected, admin.id)
    db_session.refresh(p); db_session.refresh(shadow)
    assert shadow.status == OfferStatus.rejected
    assert p.status == OfferStatus.published
