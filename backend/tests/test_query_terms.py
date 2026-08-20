from app.crud import query_term as qt
from app.models.enums import QueryTermStatus
from app.schemas.query_term import QueryTermCandidate


def _c(term, z=1.0, support=3):
    return QueryTermCandidate(term=term, z=z, support=support)


def test_upsert_inserts_pending(db_session):
    n = qt.upsert_candidates(db_session, [_c("імплантація"), _c("зуби")])
    assert n == 2
    pend = qt.list_terms(db_session, QueryTermStatus.pending)
    assert {t.term for t in pend} == {"імплантація", "зуби"}


def test_reupsert_refreshes_pending(db_session):
    qt.upsert_candidates(db_session, [_c("окуляри", z=1.0, support=3)])
    qt.upsert_candidates(db_session, [_c("окуляри", z=2.5, support=9)])
    row = qt.list_terms(db_session, QueryTermStatus.pending)[0]
    assert row.z == 2.5 and row.support == 9


def test_approve_then_reupsert_keeps_approved(db_session):
    qt.upsert_candidates(db_session, [_c("стоматологія")])
    row = qt.list_terms(db_session)[0]
    qt.approve(db_session, row.id, reviewed_by=1)
    assert qt.list_approved_terms(db_session) == ["стоматологія"]
    qt.upsert_candidates(db_session, [_c("стоматологія", z=9.9)])   # must not revert
    db_session.refresh(row)
    assert row.status == QueryTermStatus.approved and row.z != 9.9


def test_reject_excludes_from_approved(db_session):
    qt.upsert_candidates(db_session, [_c("сміття")])
    row = qt.list_terms(db_session)[0]
    qt.reject(db_session, row.id, reviewed_by=1)
    assert "сміття" not in qt.list_approved_terms(db_session)
    assert row.reviewed_by == 1 and row.reviewed_at is not None


def test_to_pending_unrejects_and_clears_review(db_session):
    qt.upsert_candidates(db_session, [_c("манікюр")])
    row = qt.list_terms(db_session)[0]
    qt.reject(db_session, row.id, reviewed_by=7)
    assert row.status == QueryTermStatus.rejected and row.reviewed_by == 7
    qt.to_pending(db_session, row.id)
    db_session.refresh(row)
    assert row.status == QueryTermStatus.pending          # back in candidates
    assert row.reviewed_by is None and row.reviewed_at is None   # review stamp cleared
    assert "манікюр" not in qt.list_rejected_terms(db_session)   # crawler stops excluding


def test_list_rejected_terms(db_session):
    qt.upsert_candidates(db_session, [_c("грн"), _c("зуби")])
    grn = next(r for r in qt.list_terms(db_session) if r.term == "грн")
    qt.reject(db_session, grn.id, reviewed_by=1)
    assert qt.list_rejected_terms(db_session) == ["грн"]      # only rejected
    assert "зуби" not in qt.list_rejected_terms(db_session)   # pending excluded
