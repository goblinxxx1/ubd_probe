from app.crud import offer as offer_crud
from app.models import Offer
from app.models.offer_link import OfferLink
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate, OfferUpdate


def _create(db, **over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://old-site", article_url="https://old-article",
                target_url="https://biz/deal")
    base.update(over)
    return offer_crud.create_offer(db, OfferCreate(**base), CreatedBy.crawler, OfferStatus.pending_review)


def test_update_syncs_single_link(db_session):
    o = _create(db_session)
    assert len(o.links) == 1
    offer_crud.update_offer(db_session, o.id,
                            OfferUpdate(site_url="https://new-site", article_url="https://new-article"))
    db_session.refresh(o)
    assert len(o.links) == 1
    assert o.links[0].site_url == "https://new-site"
    assert o.links[0].article_url == "https://new-article"


def test_update_creates_link_when_none(db_session):
    o = Offer(type="discount", title="T", description="", provider="P",
              status=OfferStatus.pending_review, created_by=CreatedBy.admin,
              site_url="https://old-site", article_url="https://old-article")
    db_session.add(o); db_session.commit(); db_session.refresh(o)
    assert len(o.links) == 0
    offer_crud.update_offer(db_session, o.id, OfferUpdate(site_url="https://new-site"))
    db_session.refresh(o)
    assert len(o.links) == 1
    assert o.links[0].site_url == "https://new-site"


def test_update_multilink_syncs_only_matching(db_session):
    o = _create(db_session)                      # 1 link at old-site/old-article
    o.links.append(OfferLink(provider="Other", site_url="https://other-site",
                             article_url="https://other-article"))
    db_session.commit(); db_session.refresh(o)
    assert len(o.links) == 2
    offer_crud.update_offer(db_session, o.id,
                            OfferUpdate(site_url="https://new-site", article_url="https://new-article"))
    db_session.refresh(o)
    matched = [l for l in o.links if l.site_url == "https://new-site"]
    other = [l for l in o.links if l.provider == "Other"]
    assert len(matched) == 1 and matched[0].article_url == "https://new-article"
    assert len(other) == 1 and other[0].site_url == "https://other-site"   # untouched
