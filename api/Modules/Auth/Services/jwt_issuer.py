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
    across the HTTP response.

    ``session_id`` is the stable per-login UUID minted by
    ``Services.refresh.issue`` (and propagated through every
    rotation). Embedding it in the access token lets every
    request know which session it belongs to without an extra DB
    lookup — the sessions panel uses it to flag "This device".
    """
    sub: int  # user id
    role: str
    store_id: int | None
    permissions: list[str]
    full_name: str = ""
    username: str = ""
    session_id: str | None = None


def issue_access_token(
    issuer: JWTIssuer, *, ttl_seconds: int = DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
) -> str:
    """Mint an HS256 JWT carrying the issuer's claims. Returns the
    encoded token string."""
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(issuer.sub),
        "role": issuer.role,
        "store_id": issuer.store_id,
        "perms": list(issuer.permissions),
        "name": issuer.full_name,
        "username": issuer.username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    if issuer.session_id is not None:
        payload["sid"] = issuer.session_id
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify + decode a token. Raises `jwt.InvalidTokenError` (or a
    subclass: `ExpiredSignatureError`, `InvalidSignatureError`, etc.)
    on failure — callers translate into 401.

    Refuses tokens carrying a `purpose` claim — those are limited-
    purpose tokens (e.g. the 2FA-pending hop), not full access
    tokens. A pending token slipped into an Authorization header
    must NOT authorise an authenticated request.
    """
    claims = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    if claims.get("purpose"):
        raise jwt.InvalidTokenError(
            "Token has a purpose claim and cannot authorise access",
        )
    return claims


# 5 minutes — long enough for the user to read their authenticator
# app, short enough that a captured pending token can't be used to
# resume a session hours later. Recovery codes use the same TTL.
DEFAULT_PENDING_2FA_TTL_SECONDS = 5 * 60


def issue_pending_2fa_token(
    user_id: int,
    *,
    ttl_seconds: int = DEFAULT_PENDING_2FA_TTL_SECONDS,
) -> str:
    """Mint a short-lived JWT representing "this user has passed
    password auth but still needs to clear the 2FA hop". The
    `/auth/login/totp` and `/auth/login/recovery` endpoints exchange
    this for a full access token after verifying the second factor.

    Carries `purpose: "totp-pending"` so it can't be smuggled into
    an Authorization header — `decode_access_token` rejects any
    token with a purpose claim.
    """
    now = _now()
    payload = {
        "sub": str(user_id),
        "purpose": "totp-pending",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_pending_2fa_token(token: str) -> dict[str, Any]:
    """Verify + decode a 2FA-pending token. Raises
    `jwt.InvalidTokenError` if the token is invalid, expired, or
    isn't a pending token (wrong / missing purpose claim)."""
    claims = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    if claims.get("purpose") != "totp-pending":
        raise jwt.InvalidTokenError("Not a 2FA-pending token")
    return claims


# 5 minutes is the same TTL as the 2FA-pending token. Long enough
# for the user's authenticator UI / OS prompt to resolve, short
# enough that a stolen token can't be replayed later.
DEFAULT_PASSKEY_REGISTER_TTL_SECONDS = 5 * 60


def issue_passkey_register_token(
    user_id: int, challenge_b64: str,
    *,
    ttl_seconds: int = DEFAULT_PASSKEY_REGISTER_TTL_SECONDS,
) -> str:
    """Mint a short-lived JWT carrying the WebAuthn registration
    challenge between the SPA's begin/finish round-trip. The
    challenge itself is base64url-encoded inside the token claims —
    the FastAPI flow can't use Flask's session like the legacy
    routes did, so the token IS the state."""
    now = _now()
    payload = {
        "sub":       str(user_id),
        "purpose":   "passkey-register",
        "challenge": challenge_b64,
        "iat":       int(now.timestamp()),
        "exp":       int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_passkey_register_token(token: str) -> dict[str, Any]:
    """Verify + decode a passkey-register token. Raises
    `jwt.InvalidTokenError` on invalid / expired / wrong-purpose
    tokens. The challenge sits in `claims["challenge"]` as
    base64url; the caller decodes it back to bytes via
    `webauthn.helpers.base64url_to_bytes`."""
    claims = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    if claims.get("purpose") != "passkey-register":
        raise jwt.InvalidTokenError("Not a passkey-register token")
    return claims
