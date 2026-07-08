from app.models import AdminUser, OfferCategory, TargetCategory
from app.models.enums import AdminRole
from app.seed import seed


def test_seed_is_idempotent(db_session):
    seed(db_session)
    seed(db_session)  # second run must not duplicate
    admins = db_session.query(AdminUser).all()
    assert len(admins) == 1
    assert admins[0].role == AdminRole.super_admin
    assert db_session.query(TargetCategory).count() == 5
    assert db_session.query(OfferCategory).count() == 7
