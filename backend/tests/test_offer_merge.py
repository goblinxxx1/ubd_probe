from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(target, provider="P", site="https://a/x", article="https://a/x", title="T", val="10"):
    return OfferCreate(type="discount", title=title, provider=provider,
                       discount_type="percent", discount_value=val,
                       site_url=site, article_url=article, target_url=target)


def _create(db, data):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, OfferStatus.pending_review)


def test_same_target_merges_into_one_offer_with_two_links(db_session):
    a = _create(db_session, _offer("https://biz.example/deal", provider="Agg1",
                                    site="https://agg1", article="https://agg1/p"))
    b = _create(db_session, _offer("https://biz.example/deal", provider="Agg2",
                                    site="https://agg2", article="https://agg2/p"))
    assert a.id == b.id
    assert len(a.links) == 2
    assert {l.provider for l in a.links} == {"Agg1", "Agg2"}


def test_different_target_stays_separate(db_session):
    a = _create(db_session, _offer("https://biz.example/one"))
    b = _create(db_session, _offer("https://biz.example/two"))
    assert a.id != b.id


def test_no_target_stays_separate(db_session):
    a = _create(db_session, _offer(None))
    b = _create(db_session, _offer(None))
    assert a.id != b.id


def test_merge_is_idempotent(db_session):
    a = _create(db_session, _offer("https://biz.example/deal", provider="Agg1",
                                    site="https://agg1", article="https://agg1/p"))
    b = _create(db_session, _offer("https://biz.example/deal", provider="Agg1",
                                    site="https://agg1", article="https://agg1/p"))
    assert a.id == b.id
    assert len(a.links) == 1
