from app.models import BlockedHost
from app.models.enums import BlockedHostStatus


def test_blocked_host_model_defaults(db_session):
    obj = BlockedHost(host="nv.example", media_ratio=0.9, aggregator_ratio=0.1, support=4)
    db_session.add(obj)
    db_session.commit()
    db_session.refresh(obj)
    assert obj.id is not None
    assert obj.status == BlockedHostStatus.pending
    assert obj.created_at is not None


from app.crud import blocked_host as bh_crud
from app.schemas.blocked_host import HostCandidateCreate


def _cand(host="nv.example"):
    return HostCandidateCreate(host=host, media_ratio=0.9, aggregator_ratio=0.1,
                               support=4, sample_urls=["https://nv.example/a"])


def test_upsert_is_idempotent_on_host(db_session):
    a = bh_crud.upsert_candidate(db_session, _cand())
    b = bh_crud.upsert_candidate(db_session, _cand())
    assert a.id == b.id
    assert len(bh_crud.list_hosts(db_session)) == 1


def test_approve_puts_host_in_approved_list(db_session):
    c = bh_crud.upsert_candidate(db_session, _cand("media.example"))
    bh_crud.approve(db_session, c.id, reviewed_by=1)
    assert "media.example" in bh_crud.list_approved_hosts(db_session)


def test_reject_excludes_from_approved(db_session):
    c = bh_crud.upsert_candidate(db_session, _cand("ok.example"))
    bh_crud.reject(db_session, c.id, reviewed_by=1)
    assert "ok.example" not in bh_crud.list_approved_hosts(db_session)
    # re-submitting a rejected host does not resurrect it to pending
    bh_crud.upsert_candidate(db_session, _cand("ok.example"))
    assert bh_crud.get(db_session, c.id).status.value == "rejected"
