import json

import httpx

from crawler.api_client import ApiClient


def _handler(captured):
    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/api/internal/sources":
            return httpx.Response(200, json=[{"id": 1, "type": "website",
                                              "url_or_handle": "http://x", "name": "X"}])
        if request.url.path.endswith("/crawl-state") and request.method == "GET":
            return httpx.Response(200, json={"last_seen_key": "p1", "last_crawled_at": None})
        if request.url.path == "/api/internal/offers":
            return httpx.Response(200, json={"id": 7, "status": "pending_review"})
        if request.url.path == "/api/internal/offer-categories":
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": 42, "name": body["name"],
                                             "slug": body["slug"]})
        return httpx.Response(404, json={"code": "not_found", "detail": "x"})
    return handle


def test_list_sources_sends_api_key():
    captured = []
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(_handler(captured)))
    sources = client.list_sources()
    assert sources[0]["id"] == 1
    assert captured[0].headers["X-API-Key"] == "secret"


def test_submit_offer_posts_payload():
    captured = []
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(_handler(captured)))
    out = client.submit_offer({"type": "discount", "title": "t", "provider": "p"})
    assert out["id"] == 7
    body = json.loads(captured[-1].content)
    assert body["title"] == "t"


def test_create_offer_category_posts_name_and_slug():
    captured = []
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(_handler(captured)))
    out = client.create_offer_category("Автосервіс", "auto")
    assert out["id"] == 42
    assert captured[-1].url.path == "/api/internal/offer-categories"
    assert captured[-1].headers["X-API-Key"] == "secret"
    body = json.loads(captured[-1].content)
    assert body == {"name": "Автосервіс", "slug": "auto"}


def test_list_rejected_offers_calls_endpoint():
    seen = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"host": "news.ua", "rejected_at": None}])

    client = ApiClient("http://api", "secret", 10.0, transport=httpx.MockTransport(handle))
    rows = client.list_rejected_offers("2026-08-01T00:00:00")
    assert rows == [{"host": "news.ua", "rejected_at": None}]
    assert "/api/internal/rejected-offers" in seen["url"]
    assert "since=2026-08-01" in seen["url"]
