import importlib.util
import pathlib

from app.crud import blocked_host as bh


def _load():
    versions = (pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions")
    path = next(versions.glob("*seed_russian_apex_blocklist.py"))
    spec = importlib.util.spec_from_file_location("mig_seed_ru_apex", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ru_apex_seed_inserts_approved_idempotently(db_session):
    mod = _load()
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    approved = bh.list_approved_hosts(db_session)
    assert "boombate.com" in approved
    assert set(mod.SEED_HOSTS).issubset(set(approved))
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    assert bh.list_approved_hosts(db_session).count("boombate.com") == 1
