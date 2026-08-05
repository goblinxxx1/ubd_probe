from app.crud import offer as offer_crud
from app.crud import blocked_host as bh
from app.schemas.offer import OfferCreate
from app.models.enums import CreatedBy, OfferStatus


def _crawler(db, **kw):
    data = OfferCreate(type="discount", title=kw.pop("title", "T"),
                       provider=kw.pop("provider", "Biz"), **kw)
    return offer_crud.create_offer(db, data, CreatedBy.crawler, OfferStatus.pending_review)


def test_gate_rejects_offer_from_blocked_site_host(db_session):
    bh.auto_block(db_session, "fraza.ua")
    o = _crawler(db_session, site_url="https://fraza.ua/x", article_url="https://fraza.ua/x",
                 provider="uglovoy.com.ua", target_url="https://uglovoy.com.ua")
    assert o.status == OfferStatus.rejected


def test_gate_matches_subdomain_of_blocked_host(db_session):
    bh.auto_block(db_session, "znaj.ua")
    o = _crawler(db_session, article_url="https://breaking.znaj.ua/post", provider="Shop")
    assert o.status == OfferStatus.rejected


def test_gate_rejects_on_blocked_provider_host(db_session):
    bh.auto_block(db_session, "google.com")
    o = _crawler(db_session, provider="google.com", site_url="https://google.com/x")
    assert o.status == OfferStatus.rejected


def test_gate_passes_clean_business_host(db_session):
    o = _crawler(db_session, site_url="https://reima.ua/mil", provider="reima.ua",
                 target_url="https://reima.ua")
    assert o.status == OfferStatus.pending_review


def test_gate_ignores_admin_offers(db_session):
    bh.auto_block(db_session, "fraza.ua")
    data = OfferCreate(type="discount", title="T", provider="fraza.ua",
                       site_url="https://fraza.ua/x")
    o = offer_crud.create_offer(db_session, data, CreatedBy.admin, OfferStatus.published)
    assert o.status == OfferStatus.published   # admin path untouched


def _mk(db, status, **kw):
    from app.models.offer import Offer
    from app.models.enums import OfferType
    o = Offer(type=OfferType.discount, title="T", description="", provider=kw.get("provider", "P"),
              status=status, created_by=CreatedBy.crawler,
              site_url=kw.get("site_url"), article_url=kw.get("article_url"))
    db.add(o); db.commit(); db.refresh(o)
    return o


def _admin(db):
    # Offer.reviewed_by has a real FK to admin_users.id (unlike BlockedHost.reviewed_by, which
    # is a plain nullable int) -> a literal reviewed_by=1 fails FK on MySQL. Match the convention
    # used by test_offer_freshness.py / test_offer_shadow.py: create a real AdminUser row.
    from app.models import AdminUser
    from app.models.enums import AdminRole
    admin = AdminUser(email="learn@example.com", password_hash="x", role=AdminRole.moderator)
    db.add(admin); db.commit()
    return admin


def test_learn_blocks_host_after_second_reject_zero_published(db_session):
    admin = _admin(db_session)
    _mk(db_session, OfferStatus.rejected, article_url="https://ogo.ua/a")
    o2 = _mk(db_session, OfferStatus.pending_review, article_url="https://ogo.ua/b")
    offer_crud.set_status(db_session, o2.id, OfferStatus.rejected, reviewed_by=admin.id)
    assert "ogo.ua" in bh.list_approved_hosts(db_session)


def test_learn_does_not_block_host_with_a_published_offer(db_session):
    admin = _admin(db_session)
    _mk(db_session, OfferStatus.published, site_url="https://reima.ua/x")
    _mk(db_session, OfferStatus.rejected, site_url="https://reima.ua/y")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://reima.ua/z")
    offer_crud.set_status(db_session, o.id, OfferStatus.rejected, reviewed_by=admin.id)
    assert "reima.ua" not in bh.list_approved_hosts(db_session)


def test_learn_requires_two_rejections(db_session):
    admin = _admin(db_session)
    o = _mk(db_session, OfferStatus.pending_review, article_url="https://izum.ua/a")
    offer_crud.set_status(db_session, o.id, OfferStatus.rejected, reviewed_by=admin.id)
    assert "izum.ua" not in bh.list_approved_hosts(db_session)   # only 1 rejected so far
