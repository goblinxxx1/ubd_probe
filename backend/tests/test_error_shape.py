def test_unknown_route_has_error_shape(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"detail", "code"}
    assert body["code"] == "http_error"
