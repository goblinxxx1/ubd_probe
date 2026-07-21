from app.crud import offer as offer_crud
from app.models import Offer, Source
from app.models.enums import CreatedBy, OfferStatus, SourceType
from app.schemas.offer import OfferCreate
from app.services import promotion


def _crawler_offer(db, **over):
    base = dict(type="discount", title="T", provider="Shop",
                site_url="https://shop.example/deal", article_url="https://shop.example/deal")
    base.update(over)
    o = offer_crud.create_offer(db, OfferCreate(**base), CreatedBy.crawler,
                                OfferStatus.published, content_hash=over.get("content_hash", "h1"))
    return o


def test_publish_promotes_website_origin(db_session):
    o = _crawler_offer(db_session)
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    src = db_session.get(Source, o.source_id)
    assert src is not None
    assert src.type == SourceType.website
    assert src.url_or_handle == "https://shop.example/deal"
    assert src.name == "Shop"           # name == provider -> stable content_hash on re-crawl
    assert src.is_active is True
    assert o.last_seen_at is not None


def test_promotion_is_idempotent_across_offers_sharing_origin(db_session):
    o1 = _crawler_offer(db_session, content_hash="h1")
    o2 = _crawler_offer(db_session, title="T2", content_hash="h2")
    promotion.maybe_promote_on_publish(db_session, o1)
    promotion.maybe_promote_on_publish(db_session, o2)
    db_session.refresh(o1); db_session.refresh(o2)
    assert o1.source_id == o2.source_id
    assert db_session.query(Source).count() == 1


def test_no_promotion_for_admin_offer(db_session):
    o = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="T", provider="P",
                                site_url="https://shop.example/deal"),
        CreatedBy.admin, OfferStatus.published, content_hash="h1")
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    assert o.source_id is None
    assert db_session.query(Source).count() == 0


def test_no_promotion_without_site_url(db_session):
    o = _crawler_offer(db_session, site_url=None)
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    assert o.source_id is None
    assert db_session.query(Source).count() == 0


def test_no_promotion_when_already_sourced(db_session):
    from app.crud import source as source_crud
    from app.schemas.source import SourceCreate
    s = source_crud.create_source(
        db_session, SourceCreate(name="Existing", type="website",
                                 url_or_handle="https://other/x", is_active=True),
        CreatedBy.admin)
    o = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="T", provider="Shop",
                                site_url="https://shop.example/deal"),
        CreatedBy.crawler, OfferStatus.published, source_id=s.id, content_hash="h1")
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    assert o.source_id == s.id           # unchanged
    assert db_session.query(Source).count() == 1


def test_promotion_respects_unique_constraint(db_session):
    # A source already exists for the origin, with an offer holding (source_id, "h1").
    from app.crud import source as source_crud
    from app.schemas.source import SourceCreate
    s = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/deal", "Shop", CreatedBy.crawler)
    offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="Prior", provider="Shop",
                                site_url="https://shop.example/deal"),
        CreatedBy.crawler, OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    # New offer, same origin, same content_hash, not yet sourced.
    o = _crawler_offer(db_session, content_hash="h1")
    promotion.maybe_promote_on_publish(db_session, o)   # must not raise / must not violate uq
    db_session.refresh(o)
    assert o.source_id is None           # left unlinked; existing row already represents it


def test_publish_endpoint_promotes(client, db_session):
    from app.core.security import create_access_token
    from app.models import AdminUser
    from app.models.enums import AdminRole
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin); db_session.commit()
    token = create_access_token(subject=admin.email, role="moderator")

    pending = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="Crawled", provider="Shop",
                                site_url="https://shop.example/deal"),
        CreatedBy.crawler, OfferStatus.pending_review, content_hash="h1")

    r = client.post(f"/api/admin/offers/{pending.id}/publish",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["status"] == "published"
    db_session.refresh(pending)
    assert pending.source_id is not None
    assert db_session.get(Source, pending.source_id).name == "Shop"
