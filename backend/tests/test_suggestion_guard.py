from app.crud import source as source_crud
from app.crud import suggested_source as suggestion_crud
from app.models import SuggestedSource
from app.models.enums import CreatedBy
from app.schemas.source import SourceCreate
from app.schemas.suggested_source import SuggestedSourceCreate


def _active_source(db, type_, ref):
    return source_crud.create_source(
        db, SourceCreate(name="S", type=type_, url_or_handle=ref, is_active=True),
        CreatedBy.crawler)


def test_suggestion_for_active_source_is_skipped(db_session):
    _active_source(db_session, "website", "https://biz.example/")
    out = suggestion_crud.create_suggestion(
        db_session, SuggestedSourceCreate(name="X", type="website",
                                          url_or_handle="http://www.biz.example"))
    assert out is None
    assert db_session.query(SuggestedSource).count() == 0


def test_suggestion_for_active_telegram_is_skipped(db_session):
    _active_source(db_session, "telegram", "https://t.me/mychan")
    out = suggestion_crud.create_suggestion(
        db_session, SuggestedSourceCreate(name="X", type="telegram", url_or_handle="@mychan"))
    assert out is None


def test_new_source_still_suggested(db_session):
    _active_source(db_session, "website", "https://biz.example/")
    out = suggestion_crud.create_suggestion(
        db_session, SuggestedSourceCreate(name="X", type="website",
                                          url_or_handle="https://other.example"))
    assert out is not None
    assert db_session.query(SuggestedSource).count() == 1
