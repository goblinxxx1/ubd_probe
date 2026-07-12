from app.core.config import settings


def test_bot_account_upsert_and_list(client, db_session):
    h = {"X-API-Key": settings.crawler_api_key}
    r1 = client.post("/api/internal/bot-accounts/instagram/bot_one/state",
                     json={"state": "banned"}, headers=h)
    assert r1.status_code == 200
    assert r1.json()["state"] == "banned"
    assert r1.json()["username"] == "bot_one"

    # upsert again (same row), flip state
    r2 = client.post("/api/internal/bot-accounts/instagram/bot_one/state",
                     json={"state": "active"}, headers=h)
    assert r2.json()["state"] == "active"

    lst = client.get("/api/internal/bot-accounts?platform=instagram", headers=h)
    assert lst.status_code == 200
    assert len(lst.json()) == 1
    assert lst.json()[0]["username"] == "bot_one"


def test_bot_accounts_require_api_key(client, db_session):
    assert client.get("/api/internal/bot-accounts").status_code == 401
