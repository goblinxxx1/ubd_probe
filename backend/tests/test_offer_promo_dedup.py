from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _source(db, url):
    # Offer.source_id is a real FK -> sources.id; a literal id like 20/23 with no row
    # would fail on insert with an unrelated IntegrityError, not the behavior under test.
    return source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle=url, is_active=True),
        CreatedBy.crawler)


def _offer(article, *, host, desc, val="15", label=None, discounts=None, title="Бізнес"):
    if discounts is None:
        discounts = [{"discount_type": "percent", "discount_value": val, "label": label}]
    return OfferCreate(
        type="discount", title=title, provider="P", description=desc,
        discount_type=discounts[0]["discount_type"],
        discount_value=discounts[0].get("discount_value"),
        discounts=discounts,
        site_url=f"https://{host}", article_url=f"https://{host}{article}",
        target_url=f"https://{host}{article}")


def _cr(db, data, status=OfferStatus.pending_review, source_id=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status, source_id=source_id)


def test_reworded_same_promo_on_other_page_collapses(db_session):
    a = _cr(db_session, _offer("/", host="edclinic.com.ua",
            desc="Знижка 15% військовим на всі медичні послуги клініки", label="15% військовим"),
            status=OfferStatus.published)
    b = _cr(db_session, _offer("/pro-nas", host="edclinic.com.ua",
            desc="Військовим знижка 15% на послуги нашої медичної клініки", label="для захисників"))
    assert b.id == a.id


def test_same_percent_different_promo_stays_separate(db_session):
    a = _cr(db_session, _offer("/kava", host="cafe.com.ua", val="10",
            desc="Знижка 10% на каву студентам", label="10% кава"))
    b = _cr(db_session, _offer("/strizhka", host="cafe.com.ua", val="10",
            desc="Знижка 10% на стрижку військовим", label="10% стрижка"))
    assert a.id != b.id


def test_new_offer_collapses_onto_pending_shadow(db_session):
    src = _source(db_session, "https://dentalstudio.ck.ua")
    pub = _cr(db_session, _offer("/aktsiyi", host="dentalstudio.ck.ua", val="10",
              desc="Знижка 10% пенсіонерам клініки", label="10%"),
              status=OfferStatus.published, source_id=src.id)
    shadow = _cr(db_session, _offer("/aktsiyi", host="dentalstudio.ck.ua", val="15",
                 desc="Знижка 15% для військових Dental Studio", label="знижка 15% для військових"),
                 source_id=src.id)
    assert shadow.supersedes_offer_id == pub.id
    dup = _cr(db_session, _offer("/pro-nas", host="dentalstudio.ck.ua", val="15",
              desc="Dental Studio знижка 15% для військових", label="знижка 15% для військових"),
              source_id=src.id)
    assert dup.id == shadow.id


def test_multi_discount_subset_collapses(db_session):
    src = _source(db_session, "https://tovpollar.org")
    pub = _cr(db_session, _offer("/aktsii", host="tovpollar.org",
              desc="Знижки військовим 30% та ветеранам 50% на продукцію",
              discounts=[{"discount_type": "percent", "discount_value": "30", "label": "30% військовим"},
                         {"discount_type": "percent", "discount_value": "50", "label": "50% ветеранам"}]),
              status=OfferStatus.published, source_id=src.id)
    b = _cr(db_session, _offer("/pro-nas", host="tovpollar.org",
            desc="Знижки військовим 30% на продукцію ветеранам",
            discounts=[{"discount_type": "percent", "discount_value": "30", "label": "30% військовим"}]),
            source_id=src.id)
    assert b.id == pub.id
