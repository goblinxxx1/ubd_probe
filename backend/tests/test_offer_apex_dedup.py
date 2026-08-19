from datetime import datetime

from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _offer(article, *, val="30", dtype="percent", provider="P", title="T",
           site="https://smartlab.ua"):
    return OfferCreate(type="discount", title=title, provider=provider,
                       discount_type=dtype, discount_value=val,
                       site_url=site, article_url=article)


def _create(db, data, *, status=OfferStatus.pending_review, ch=None, source_id=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status,
                                   source_id=source_id, content_hash=ch)


def _source(db, url="https://smartlab.ua"):
    return source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle=url, is_active=True),
        CreatedBy.crawler)


def test_apex_offer_collapses_onto_deep_same_host_same_magnitude(db_session):
    deep = _create(db_session, _offer("https://smartlab.ua/discont/hersona/about"),
                   status=OfferStatus.published, ch="h1")
    deep.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    apex = _create(db_session, _offer("https://smartlab.ua", val="30"), ch="h2")
    assert apex.id == deep.id                             # collapsed, not a new row
    assert db_session.query(Offer).count() == 1
    assert deep.last_seen_at > datetime(2000, 1, 1)       # bumped


def test_apex_offer_with_no_same_host_peer_is_kept(db_session):
    apex = _create(db_session, _offer("https://smartlab.ua"), ch="h1")
    assert db_session.query(Offer).count() == 1
    assert apex.article_url_canonical == "smartlab.ua"


def test_apex_offer_with_different_magnitude_is_kept(db_session):
    deep = _create(db_session, _offer("https://smartlab.ua/deep", val="30"),
                   status=OfferStatus.published, ch="h1")
    apex = _create(db_session, _offer("https://smartlab.ua", val="10"), ch="h2")
    assert apex.id != deep.id                             # 10% vs 30% -> not collapsed
    assert db_session.query(Offer).count() == 2


def test_deep_offer_is_unaffected_by_apex_branch(db_session):
    a = _create(db_session, _offer("https://smartlab.ua/one", val="30"), ch="h1")
    b = _create(db_session, _offer("https://smartlab.ua/two", val="30"), ch="h2")
    assert a.id != b.id                                   # two deep pages stay separate here


def test_shadow_peer_is_not_a_collapse_target(db_session):
    s = _source(db_session)
    parent = _create(db_session, _offer("https://smartlab.ua/deep", val="30"),
                     status=OfferStatus.published, source_id=s.id, ch="h1")
    # a shadow of the parent (branch 2: same source + deep canon + published parent)
    shadow = _create(db_session, _offer("https://smartlab.ua/deep", val="40"),
                     source_id=s.id, ch="h2")
    assert shadow.supersedes_offer_id == parent.id        # sanity: it is a shadow
    # distinct promo text so 3c's text gate does NOT fire — isolates branch 3d, which must
    # skip the shadow (supersedes IS NULL filter); the only 40% peer is the shadow, so the
    # apex is kept as a new row rather than folded onto the shadow.
    apex = _create(db_session, _offer("https://smartlab.ua", val="40",
                                      title="Absolutely unrelated apex banner wording"),
                   source_id=s.id, ch="h3")
    assert apex.id != shadow.id                           # never collapses onto a shadow
    assert apex.supersedes_offer_id is None               # kept as an independent row
