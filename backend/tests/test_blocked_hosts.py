from app.crud import blocked_host as bh_crud
from app.models import BlockedHost
from app.models.enums import BlockedHostStatus


def test_blocked_host_model_defaults(db_session):
    obj = BlockedHost(host="nv.example")
    db_session.add(obj)
    db_session.commit()
    db_session.refresh(obj)
    assert obj.id is not None
    assert obj.status == BlockedHostStatus.pending
    assert obj.created_at is not None


def test_add_manual_blocks_host_into_approved_list(db_session):
    obj = bh_crud.add_manual(db_session, "https://www.Media.example/news", reviewed_by=1)
    assert obj.host == "media.example"                    # scheme/path/www stripped
    assert obj.status == BlockedHostStatus.approved
    assert "media.example" in bh_crud.list_approved_hosts(db_session)


def test_unblock_removes_from_approved_and_can_reblock(db_session):
    obj = bh_crud.add_manual(db_session, "ok.example", reviewed_by=1)
    bh_crud.reject(db_session, obj.id, reviewed_by=1)     # unblock = reject
    assert "ok.example" not in bh_crud.list_approved_hosts(db_session)
    again = bh_crud.add_manual(db_session, "ok.example", reviewed_by=1)   # re-block
    assert again.id == obj.id                             # same row, no duplicate
    assert "ok.example" in bh_crud.list_approved_hosts(db_session)
    assert len(bh_crud.list_hosts(db_session)) == 1


def test_auto_block_creates_approved_system_row(db_session):
    obj = bh_crud.auto_block(db_session, "Fraza.UA")
    assert obj.host == "fraza.ua"
    assert obj.status == BlockedHostStatus.approved
    assert obj.reviewed_by is None
    assert "fraza.ua" in bh_crud.list_approved_hosts(db_session)


def test_auto_block_is_idempotent(db_session):
    bh_crud.auto_block(db_session, "znaj.ua")
    bh_crud.auto_block(db_session, "znaj.ua")
    approved = bh_crud.list_approved_hosts(db_session)
    assert approved.count("znaj.ua") == 1


def test_bare_host_is_public(db_session):
    from app.crud.blocked_host import bare_host
    assert bare_host("https://www.Focus.ua/x?y=1") == "focus.ua"
    assert bare_host("") == ""
