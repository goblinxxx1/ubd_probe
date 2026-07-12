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
