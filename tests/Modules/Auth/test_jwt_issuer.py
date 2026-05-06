"""Unit tests for the JWT issuer."""
import time

import jwt
import pytest


def test_issue_and_decode_round_trip():
    from api.Modules.Auth.Services import (
        JWTIssuer, decode_access_token, issue_access_token,
    )
    issuer = JWTIssuer(
        sub=42, role="admin", store_id=1,
        permissions=["store.admin", "store.employee"],
        full_name="Alice", username="alice@x.com",
    )
    token = issue_access_token(issuer)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["store_id"] == 1
    assert set(payload["perms"]) == {"store.admin", "store.employee"}
    assert payload["name"] == "Alice"
    assert payload["username"] == "alice@x.com"
    assert "iat" in payload
    assert "exp" in payload


def test_issue_default_ttl_is_30_minutes():
    from api.Modules.Auth.Services import (
        JWTIssuer, decode_access_token, issue_access_token,
    )
    issuer = JWTIssuer(
        sub=1, role="employee", store_id=1, permissions=[],
    )
    token = issue_access_token(issuer)
    payload = decode_access_token(token)
    delta = payload["exp"] - payload["iat"]
    assert delta == 30 * 60


def test_issue_respects_ttl_override():
    from api.Modules.Auth.Services import (
        JWTIssuer, decode_access_token, issue_access_token,
    )
    issuer = JWTIssuer(
        sub=1, role="employee", store_id=1, permissions=[],
    )
    token = issue_access_token(issuer, ttl_seconds=60)
    payload = decode_access_token(token)
    assert payload["exp"] - payload["iat"] == 60


def test_decode_rejects_expired_token():
    """An already-expired token must raise ExpiredSignatureError."""
    from api.Modules.Auth.Services import (
        JWTIssuer, decode_access_token, issue_access_token,
    )
    issuer = JWTIssuer(
        sub=1, role="employee", store_id=1, permissions=[],
    )
    # 1-second TTL — sleep past it.
    token = issue_access_token(issuer, ttl_seconds=1)
    time.sleep(2)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_rejects_tampered_token():
    """Flipping a single byte in the token must invalidate the signature."""
    from api.Modules.Auth.Services import (
        JWTIssuer, decode_access_token, issue_access_token,
    )
    issuer = JWTIssuer(
        sub=1, role="employee", store_id=1, permissions=[],
    )
    token = issue_access_token(issuer)
    # Flip the last char — corrupts the signature.
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(tampered)


def test_decode_rejects_token_signed_with_different_secret():
    """A token signed with a different secret must fail signature check."""
    from api.Modules.Auth.Services import decode_access_token
    bogus = jwt.encode(
        {"sub": "1", "role": "admin"},
        "different-secret", algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(bogus)
