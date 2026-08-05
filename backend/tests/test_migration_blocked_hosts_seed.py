import importlib.util
import pathlib

from app.crud import blocked_host as bh


def _load():
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "d4e6f8a0b2c4_seed_media_blocklist.py")
    spec = importlib.util.spec_from_file_location("mig_seed_blocklist", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_inserts_approved_hosts_idempotently(db_session):
    mod = _load()
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    approved = bh.list_approved_hosts(db_session)
    for h in ("fraza.ua", "znaj.ua", "google.com", "api.whatsapp.com"):
        assert h in approved
    # idempotent: second run does not duplicate
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    approved2 = bh.list_approved_hosts(db_session)
    assert approved2.count("fraza.ua") == 1
    assert set(mod.SEED_HOSTS).issubset(set(approved2))
