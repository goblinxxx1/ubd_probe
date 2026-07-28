import importlib.util
import pathlib

from sqlalchemy import text

from app.models import Offer, OfferLocation
from app.models.enums import CreatedBy, OfferStatus, OfferType


def _load_backfill():
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "a1b2c3d4e5f6_offer_locations.py")
    spec = importlib.util.spec_from_file_location("mig_offer_locations", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._backfill


def test_backfill_copies_legacy_location_into_rows(db_session):
    conn = db_session.connection()
    conn.execute(text("ALTER TABLE offers ADD COLUMN location VARCHAR(255)"))
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add(o)
    db_session.commit()
    conn = db_session.connection()  # re-acquire: commit() releases the prior handle
    conn.execute(text("UPDATE offers SET location = 'Київ' WHERE id = :i"), {"i": o.id})

    _load_backfill()(conn)

    names = [r.name for r in db_session.query(OfferLocation).filter_by(offer_id=o.id)]
    assert names == ["Київ"]
    conn.execute(text("ALTER TABLE offers DROP COLUMN location"))
