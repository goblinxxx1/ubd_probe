from app.demo_seed import demo_seed, FIXTURE_URL
from app.models.source import Source
from app.models.enums import SourceType, CreatedBy


def test_demo_seed_inserts_fixture_source(db_session):
    src = demo_seed(db_session)
    assert src.url_or_handle == FIXTURE_URL
    assert src.type == SourceType.website
    assert src.is_active is True
    assert src.created_by == CreatedBy.admin


def test_demo_seed_is_idempotent(db_session):
    demo_seed(db_session)
    demo_seed(db_session)  # second run must not duplicate
    rows = db_session.query(Source).filter(Source.url_or_handle == FIXTURE_URL).all()
    assert len(rows) == 1
