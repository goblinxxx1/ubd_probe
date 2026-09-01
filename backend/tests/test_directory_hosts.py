from app.core.config import settings
from app.crud import directory_host as dh
from app.models import Offer
from app.models.enums import OfferStatus, CreatedBy, OfferType

_KEY = {"X-API-Key": settings.crawler_api_key}


def _mk_offer(db, host, status=OfferStatus.pending_review, created_by=CreatedBy.crawler):
    o = Offer(type=OfferType.discount, title="t", description="", provider="P",
              status=status, created_by=created_by,
              site_url=f"https://{host}", article_url=f"https://{host}/x")
    db.add(o); db.commit(); db.refresh(o); return o


def test_register_is_idempotent(db_session):
    assert dh.register(db_session, "myhelp.com.ua") is True
    assert dh.register(db_session, "myhelp.com.ua") is False
    assert dh.list_hosts(db_session) == ["myhelp.com.ua"]


def test_register_sweeps_existing_crawler_pending_offers(db_session):
    keep_pub = _mk_offer(db_session, "myhelp.com.ua", status=OfferStatus.published)
    keep_other = _mk_offer(db_session, "otherbiz.com.ua")
    victim = _mk_offer(db_session, "myhelp.com.ua")
    dh.register(db_session, "myhelp.com.ua")
    db_session.refresh(victim); db_session.refresh(keep_pub); db_session.refresh(keep_other)
    assert victim.status == OfferStatus.rejected
    assert keep_pub.status == OfferStatus.published      # published untouched
    assert keep_other.status == OfferStatus.pending_review  # other host untouched


def test_register_sweep_leaves_non_crawler_offer_untouched(db_session):
    """Sweep must NOT touch admin-created offers (only crawlers are swept)."""
    admin_offer = _mk_offer(db_session, "myhelp.com.ua",
                            status=OfferStatus.pending_review, created_by=CreatedBy.admin)
    dh.register(db_session, "myhelp.com.ua")
    db_session.refresh(admin_offer)
    assert admin_offer.status == OfferStatus.pending_review  # non-crawler untouched


def test_internal_register_endpoint_and_sweep(client, db_session):
    o = _mk_offer(db_session, "myhelp.com.ua")
    r = client.post("/api/internal/directory-hosts", headers=_KEY, json={"host": "myhelp.com.ua"})
    assert r.status_code == 200 and r.json()["registered"] is True
    db_session.refresh(o)
    assert o.status.value == "rejected"


def test_internal_register_endpoint_requires_api_key(client, db_session):
    r = client.post("/api/internal/directory-hosts", json={"host": "myhelp.com.ua"})
    assert r.status_code == 401


def test_create_gate_rejects_new_offer_from_directory_host(client, db_session):
    client.post("/api/internal/directory-hosts", headers=_KEY, json={"host": "myhelp.com.ua"})
    payload = {"type": "discount", "title": "t", "provider": "MY Help",
               "site_url": "https://myhelp.com.ua",
               "article_url": "https://myhelp.com.ua/places/x/services/y",
               "content_hash": "hash-dir-1"}
    r = client.post("/api/internal/offers", headers=_KEY, json=payload)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
