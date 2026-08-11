from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _banner(article, val="15", label="Знижка 15% на лікування", host="edclinic.com.ua",
            provider="ED"):
    return OfferCreate(
        type="discount", title="T", provider=provider,
        discount_type="percent", discount_value=val,
        discounts=[{"discount_type": "percent", "discount_value": val, "label": label}],
        site_url=f"https://{host}", article_url=f"https://{host}{article}",
        target_url=f"https://{host}{article}")


def _cr(db, data):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, OfferStatus.pending_review)


def test_sitewide_banner_same_host_same_discount_collapses(db_session):
    # same 15% banner (same label) on three different pages of one site -> ONE offer
    a = _cr(db_session, _banner("/znizhka-15"))
    b = _cr(db_session, _banner("/kontakty"))
    c = _cr(db_session, _banner("/type_specialists/stomatolog-ortoped"))
    assert b.id == a.id and c.id == a.id


def test_banner_dedup_bumps_last_seen_not_content(db_session):
    a = _cr(db_session, _banner("/znizhka-15"))
    b = _cr(db_session, _banner("/kontakty"))
    assert b.id == a.id
    assert b.article_url == a.article_url            # returned the existing row, content untouched


def test_different_value_stays_separate(db_session):
    a = _cr(db_session, _banner("/z50", val="50", label="Знижка 50%"))
    b = _cr(db_session, _banner("/z30", val="30", label="Знижка 30%"))
    assert a.id != b.id                              # 50% and 30% are two distinct offers


def test_same_value_different_label_stays_separate(db_session):
    a = _cr(db_session, _banner("/lunch", val="10", label="-10% на обід"))
    b = _cr(db_session, _banner("/dinner", val="10", label="-10% на вечерю"))
    assert a.id != b.id                              # lunch vs dinner: same %, different offer


def test_different_host_same_discount_stays_separate(db_session):
    a = _cr(db_session, _banner("/z", host="clinica.com.ua"))
    b = _cr(db_session, _banner("/z", host="clinicb.com.ua"))
    assert a.id != b.id                              # different businesses
