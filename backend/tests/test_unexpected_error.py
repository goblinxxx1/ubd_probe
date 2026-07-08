import json

from app.main import handle_unexpected_error


def test_handle_unexpected_error_returns_uniform_shape():
    response = handle_unexpected_error(None, Exception("boom"))
    assert response.status_code == 500
    body = json.loads(response.body)
    assert body == {"detail": "Internal Server Error", "code": "internal_error"}
