import pytest

from app.core import security


def test_password_hash_roundtrip():
    hashed = security.hash_password("s3cret")
    assert hashed != "s3cret"
    assert security.verify_password("s3cret", hashed)
    assert not security.verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = security.create_access_token(subject="admin@example.com", role="super_admin")
    claims = security.decode_access_token(token)
    assert claims["sub"] == "admin@example.com"
    assert claims["role"] == "super_admin"


def test_jwt_invalid_raises():
    import jwt
    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token("not.a.token")


def test_api_key_check():
    assert security.verify_api_key(security.settings.crawler_api_key)
    assert not security.verify_api_key("wrong-key")
