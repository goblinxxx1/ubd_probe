import json

import httpx

from crawler.api_client import ApiClient


def _handler(captured):
    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/api/internal/sources":
            return httpx.Response(200, json=[{"id": 1, "type": "website",
                                              "url_or_handle": "http://x", "name": "X"}])
        if request.url.path == "/api/internal/sources/uncrawled":
            return httpx.Response(200, json=[{"id": 2, "type": "website",
                                              "url_or_handle": "http://y", "name": "Y"}])
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


def test_list_rejected_query_terms_calls_endpoint():
    seen = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=["грн", "день"])

    client = ApiClient("http://api", "secret", 10.0, transport=httpx.MockTransport(handle))
    terms = client.list_rejected_query_terms()
    assert terms == ["грн", "день"]
    assert "/api/internal/query-terms/rejected" in seen["url"]


def test_list_uncrawled_sources_sends_limit_and_key():
    captured = []
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(_handler(captured)))
    out = client.list_uncrawled_sources(7)
    assert out[0]["id"] == 2
    assert captured[0].headers["X-API-Key"] == "secret"
    assert captured[0].url.params.get("limit") == "7"


def test_auto_block_host_posts_host():
    captured = []
    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/api/internal/blocked-hosts" and request.method == "POST":
            return httpx.Response(200, json={"id": 1, "host": "dumka.media",
                "status": "approved", "media_ratio": 0.0, "aggregator_ratio": 0.0,
                "support": 0, "sample_urls": None, "reviewed_at": None,
                "created_at": "2026-08-17T00:00:00"})
        return httpx.Response(404, json={"code": "not_found", "detail": "x"})
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(handle))
    out = client.auto_block_host("dumka.media", "https://dumka.media/x")
    assert out["host"] == "dumka.media"
    sent = json.loads(captured[0].content)
    assert sent == {"host": "dumka.media", "sample_url": "https://dumka.media/x"}
    assert captured[0].headers["X-API-Key"] == "secret"
