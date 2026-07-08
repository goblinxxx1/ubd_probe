from app.core.security import create_access_token
from app.crud import offer as offer_crud
from app.models import AdminUser
from app.models.enums import AdminRole, CreatedBy, OfferStatus, OfferType
from app.schemas.offer import OfferCreate


def _admin_token(db_session):
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_moderation_queue_and_publish(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    pending = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Crawled", provider="P"),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)

    queue = client.get("/api/admin/offers?status=pending_review", headers=h).json()
    assert queue["total"] == 1

    pub = client.post(f"/api/admin/offers/{pending.id}/publish", headers=h)
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    # now visible publicly
    assert client.get("/api/offers").json()["total"] == 1


def test_admin_offers_requires_auth(client):
    assert client.get("/api/admin/offers").status_code == 401


def test_update_offer_rejects_invalid_dates_and_discount(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    published = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Deal", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.published)

    bad_dates = client.patch(f"/api/admin/offers/{published.id}",
                             json={"valid_from": "2026-08-01", "valid_until": "2026-07-01"},
                             headers=h)
    assert bad_dates.status_code == 422
    assert bad_dates.json()["code"] == "validation_error"

    bad_discount = client.patch(f"/api/admin/offers/{published.id}",
                                json={"discount_type": "free", "discount_value": 10},
                                headers=h)
    assert bad_discount.status_code == 422
    assert bad_discount.json()["code"] == "validation_error"
