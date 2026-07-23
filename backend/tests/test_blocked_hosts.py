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
