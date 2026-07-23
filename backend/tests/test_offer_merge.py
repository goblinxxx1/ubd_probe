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


from app.schemas.offer import OfferUpdate


def _create_admin(db, data):
    return offer_crud.create_offer(db, data, CreatedBy.admin, OfferStatus.published)


def test_merges_across_utm_www_and_scheme(db_session):
    a = _create(db_session, _offer("https://www.biz.example/deal?utm_source=a",
                                    provider="Agg1", site="https://agg1", article="https://agg1/p"))
    b = _create(db_session, _offer("http://biz.example/deal?fbclid=zz",
                                    provider="Agg2", site="https://agg2", article="https://agg2/p"))
    assert a.id == b.id
    assert len(a.links) == 2
    assert a.target_url_canonical == "biz.example/deal"


def test_different_canonical_stays_separate(db_session):
    a = _create(db_session, _offer("https://biz.example/one"))
    b = _create(db_session, _offer("https://biz.example/two"))
    assert a.id != b.id


def test_admin_does_not_dedup_but_stores_canonical(db_session):
    a = _create_admin(db_session, _offer("https://biz.example/deal"))
    b = _create_admin(db_session, _offer("https://biz.example/deal"))
    assert a.id != b.id                              # admin never dedups
    assert a.target_url_canonical == "biz.example/deal"
    assert b.target_url_canonical == "biz.example/deal"


def test_crawler_merges_into_existing_admin_offer(db_session):
    admin = _create_admin(db_session, _offer("https://biz.example/deal", provider="Admin",
                                             site="https://admin", article="https://admin/p"))
    crawler = _create(db_session, _offer("https://www.biz.example/deal?utm_source=x",
                                         provider="Crawl", site="https://c", article="https://c/p"))
    assert crawler.id == admin.id                    # preserved cross-created_by behavior
    assert {l.provider for l in admin.links} == {"Admin", "Crawl"}


def test_update_recomputes_canonical_only_on_target_change(db_session):
    o = _create(db_session, _offer("https://biz.example/old"))
    offer_crud.update_offer(db_session, o.id, OfferUpdate(title="new title"))
    assert o.target_url_canonical == "biz.example/old"      # unchanged
    offer_crud.update_offer(db_session, o.id, OfferUpdate(target_url="https://www.biz.example/new/"))
    assert o.target_url_canonical == "biz.example/new"      # recomputed
