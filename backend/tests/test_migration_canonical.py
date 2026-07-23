import importlib.util
import pathlib

from sqlalchemy import text

from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus, OfferType


def _load_backfill():
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "9a1c7b3e2f10_offer_target_url_canonical.py")
    spec = importlib.util.spec_from_file_location("mig_canonical", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._backfill


def test_backfill_populates_canonical_for_existing_rows(db_session):
    # Legacy rows: target_url set, canonical left NULL (Task 3 auto-set not involved here).
    o1 = Offer(type=OfferType.discount, title="T", description="", provider="P",
               target_url="https://www.biz.example/deal/?utm_source=x&fbclid=z",
               status=OfferStatus.published, created_by=CreatedBy.crawler)
    o2 = Offer(type=OfferType.discount, title="T2", description="", provider="P",
               target_url=None, status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add_all([o1, o2])
    db_session.commit()
    assert o1.target_url_canonical is None          # not set on plain construction

    _load_backfill()(db_session.connection())
    db_session.expire_all()
    assert db_session.get(Offer, o1.id).target_url_canonical == "biz.example/deal"
    assert db_session.get(Offer, o2.id).target_url_canonical is None   # no target_url → stays NULL
