import importlib.util
import pathlib

from app.models import Offer, Source
from app.models.enums import CreatedBy, OfferStatus, OfferType, SourceType


def _load(name):
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "c3d5e7f9a1b2_offer_source_dedup.py")
    spec = importlib.util.spec_from_file_location("mig_dedup", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def test_backfill_strips_pagination(db_session):
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              target_url="https://b.army/specials?page=2",
              article_url="https://b.army/specials?page=2",
              status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add(o); db_session.commit()
    _load("_backfill_canonical")(db_session.connection())
    db_session.expire_all()
    r = db_session.get(Offer, o.id)
    assert r.target_url_canonical == "b.army/specials"
    assert r.article_url_canonical == "b.army/specials"


def test_dedup_sources_keeps_owner_of_most_offers(db_session):
    s_root = Source(name="Root", type=SourceType.website, url_or_handle="https://b.army",
                    is_active=True, created_by=CreatedBy.admin)
    s_pg = Source(name="Pg", type=SourceType.website,
                  url_or_handle="https://b.army/specials?page=2", is_active=True,
                  created_by=CreatedBy.admin)
    db_session.add_all([s_root, s_pg]); db_session.commit()
    # s_pg owns an offer -> must stay active; s_root deactivated
    db_session.add(Offer(type=OfferType.discount, title="T", description="", provider="P",
                         source_id=s_pg.id, status=OfferStatus.published,
                         created_by=CreatedBy.crawler))
    db_session.commit()
    _load("_dedup_sources")(db_session.connection())
    db_session.expire_all()
    assert db_session.get(Source, s_pg.id).is_active is True
    assert db_session.get(Source, s_root.id).is_active is False


def test_reject_pending_dups_of_published(db_session):
    pub = Offer(type=OfferType.discount, title="P", description="", provider="P",
                article_url_canonical="b.army/specials", status=OfferStatus.published,
                created_by=CreatedBy.crawler)
    pend = Offer(type=OfferType.discount, title="D", description="", provider="P",
                 article_url_canonical="b.army/specials", status=OfferStatus.pending_review,
                 created_by=CreatedBy.crawler)
    db_session.add_all([pub, pend]); db_session.commit()
    _load("_reject_published_pending_dups")(db_session.connection())
    db_session.expire_all()
    assert db_session.get(Offer, pend.id).status == OfferStatus.rejected
    assert db_session.get(Offer, pub.id).status == OfferStatus.published
