"""JWT access-token issuance + verification.

Per the migration ADR: JWT-claims auth model. The full permission
set is embedded as claims at login time (so subsequent requests
don't have to re-fetch the role / store-feature flags from the DB
on every hit). Default TTL is 30 minutes. Refresh tokens with a
jti-blacklist will be added in a follow-up PR.

Symmetric HS256 with the `auth_jwt_secret` setting. We stay on a
single key during the migration window — once cutover completes
and the FastAPI surface owns auth end-to-end, we can rotate to
RS256 + key-rotation if the threat model warrants it.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from api.Core.Config import settings


# Default TTL — 30 minutes per the ADR.
DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 30 * 60

JWT_ALGORITHM = "HS256"


def _now() -> datetime:
    """UTC now — one place to mock in tests."""
    return datetime.now(tz=timezone.utc)


def _secret() -> str:
    """Resolve the JWT secret from settings. Lazy lookup so tests
    can override `settings.auth_jwt_secret` between runs."""
    secret = getattr(settings, "auth_jwt_secret", None) or settings.secret_key
    if not secret:
        raise RuntimeError(
            "JWT secret unavailable — set `AUTH_JWT_SECRET` or `SECRET_KEY`",
        )
    return secret


@dataclass
class JWTIssuer:
    """Bundle of the inputs for `issue_access_token`. A user-facing
    Service constructs one of these per logged-in user and reuses it
    across the HTTP response."""
    sub: int  # user id
    role: str
    store_id: int | None
    permissions: list[str]
    full_name: str = ""
    username: str = ""


def issue_access_token(
    issuer: JWTIssuer, *, ttl_seconds: int = DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
) -> str:
    """Mint an HS256 JWT carrying the issuer's claims. Returns the
    encoded token string."""
    now = _now()
    payload = {
        "sub": str(issuer.sub),
        "role": issuer.role,
        "store_id": issuer.store_id,
        "perms": list(issuer.permissions),
        "name": issuer.full_name,
        "username": issuer.username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify + decode a token. Raises `jwt.InvalidTokenError` (or a
    subclass: `ExpiredSignatureError`, `InvalidSignatureError`, etc.)
    on failure — callers translate into 401."""
    return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
