from app.core.config import settings
from app.core.security import create_access_token
from app.crud import crawler_health as ch
from app.models import AdminUser
from app.models.enums import AdminRole

_KEY = {"X-API-Key": settings.crawler_api_key}


def _snap(**over):
    base = {
        "backends": [{"name": "brave", "fails": 0, "cooldown_s": 0,
                      "quarantine_s": 0, "status": "healthy"}],
        "global_backoff_s": 0,
        "phrases": {"tracked": 10, "productive": 7, "starved": 0},
        "recall": {"grid_cursor": 5, "cache_entries": 100},
        "noise_hosts": [{"host": "24tv.ua", "count": 9}],
        "generated_at": "2026-09-04T10:00:00Z",
    }
    base.update(over)
    return base


# --- crud (singleton latest) ---

def test_upsert_stores_latest_singleton(db_session):
    ch.upsert_snapshot(db_session, _snap())
    ch.upsert_snapshot(db_session, _snap(global_backoff_s=42))
    row = ch.get_latest(db_session)
    assert row is not None
    assert row.snapshot["global_backoff_s"] == 42          # latest wins
    assert db_session.query(ch.CrawlerHealth).count() == 1  # exactly one row


def test_get_latest_none_when_empty(db_session):
    assert ch.get_latest(db_session) is None


# --- API: crawler POST (internal) + admin GET ---

def _admin_token(db_session):
    admin = AdminUser(email="ch@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin); db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_report_then_admin_reads(client, db_session):
    r = client.post("/api/internal/crawler-health", headers=_KEY, json=_snap(global_backoff_s=7))
    assert r.status_code == 200

    token = _admin_token(db_session)
    got = client.get("/api/admin/crawler-health", headers={"Authorization": f"Bearer {token}"})
    assert got.status_code == 200
    body = got.json()
    assert body["snapshot"]["global_backoff_s"] == 7
    assert body["reported_at"] is not None


def test_admin_reads_empty_when_no_report(client, db_session):
    token = _admin_token(db_session)
    got = client.get("/api/admin/crawler-health", headers={"Authorization": f"Bearer {token}"})
    assert got.status_code == 200
    assert got.json() is None


def test_report_requires_api_key(client, db_session):
    r = client.post("/api/internal/crawler-health", json=_snap())
    assert r.status_code == 401


def test_admin_read_requires_auth(client, db_session):
    assert client.get("/api/admin/crawler-health").status_code == 401
