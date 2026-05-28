"""WebAuthn / passkey helpers scoped to the time-clock flow.

Distinct from ``api.Modules.Auth.Services.passkey`` because
roster-side passkeys key on ``StoreEmployee.id`` (the human),
not ``User.id`` (the login). The two surfaces share the same
``rp_id`` / ``rp_name`` / ``origin`` so a single
``WEBAUTHN_RP_ID`` env var binds both kinds of credentials to
the same Relying Party.

Token-passing between begin/finish + challenge/punch follows
the same short-lived-JWT pattern as the user-side flow —
state lives in the token, not in the session (the SPA hits
JWT-only endpoints).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import jwt

from sqlalchemy.orm import Session

# Reuse the JWT algorithm + secret-resolver from the existing
# user-side passkey flow so both surfaces sign with the same
# key. ``_secret`` is a private helper — we import it via the
# module to keep the existing public API untouched.
from api.Modules.Auth.Services.jwt_issuer import (
    JWT_ALGORITHM, _secret as _jwt_secret,
)
from api.Modules.TimeClock.Models import StoreEmployeePasskey
from webauthn.helpers.structs import PublicKeyCredentialDescriptor
from api.Core.Clock import utc_now


# 5 minutes mirrors the user-side ``DEFAULT_PASSKEY_REGISTER_TTL_SECONDS``.
TIMECLOCK_PASSKEY_TTL_SECONDS = 5 * 60


# ── Exceptions ──────────────────────────────────────────────


class PasskeyNotRegisteredError(ValueError):
    """The roster member doesn't have a passkey registered yet —
    raised by the punch flow when the store's ``timeclock_require_passkey``
    toggle is True and a cashier whose roster row has no credential
    tries to clock in / out."""


# ── Lookups ─────────────────────────────────────────────────


def passkey_for_employee(
    db: Session, store_id: int, store_employee_id: int,
) -> StoreEmployeePasskey | None:
    """Return the roster member's passkey row, or None when
    they haven't registered one yet. Scoped by ``store_id``
    so a cross-tenant probe can't match."""
    return (
        db.query(StoreEmployeePasskey)
          .filter_by(
              store_id=store_id,
              store_employee_id=store_employee_id,
          )
          .one_or_none()
    )


def list_passkeys_for_store(
    db: Session, store_id: int,
) -> list[StoreEmployeePasskey]:
    """Every roster passkey at the store — feeds the admin
    credentials page so the operator can see which roster
    members are registered / pending."""
    return (
        db.query(StoreEmployeePasskey)
          .filter_by(store_id=store_id)
          .all()
    )


# ── Short-lived tokens ──────────────────────────────────────


def issue_register_token(
    *,
    store_id: int,
    store_employee_id: int,
    challenge_b64: str,
    ttl_seconds: int = TIMECLOCK_PASSKEY_TTL_SECONDS,
) -> str:
    """Mint a JWT carrying the registration challenge across
    the begin/finish round-trip. The challenge IS the state —
    no session storage involved."""
    return _encode_token(
        purpose="timeclock-passkey-register",
        store_id=store_id,
        store_employee_id=store_employee_id,
        challenge_b64=challenge_b64,
        ttl_seconds=ttl_seconds,
    )


def decode_register_token(token: str) -> dict[str, Any]:
    """Verify + decode a registration token. Raises
    ``jwt.InvalidTokenError`` on invalid / expired / wrong-purpose
    tokens."""
    return _decode_token(token, expected_purpose="timeclock-passkey-register")


def issue_assert_token(
    *,
    store_id: int,
    store_employee_id: int,
    challenge_b64: str,
    ttl_seconds: int = TIMECLOCK_PASSKEY_TTL_SECONDS,
) -> str:
    """Mint a JWT carrying an assertion challenge for the
    punch flow. The cashier's clock-in / clock-out request
    echoes this token back so the server can re-verify the
    same challenge."""
    return _encode_token(
        purpose="timeclock-passkey-assert",
        store_id=store_id,
        store_employee_id=store_employee_id,
        challenge_b64=challenge_b64,
        ttl_seconds=ttl_seconds,
    )


def decode_assert_token(token: str) -> dict[str, Any]:
    return _decode_token(token, expected_purpose="timeclock-passkey-assert")


# ── Internal helpers ────────────────────────────────────────


def _now() -> datetime:
    return utc_now()


def _encode_token(
    *,
    purpose: str,
    store_id: int,
    store_employee_id: int,
    challenge_b64: str,
    ttl_seconds: int,
) -> str:
    now = _now()
    payload = {
        "purpose":             purpose,
        "store_id":            store_id,
        "store_employee_id":   store_employee_id,
        "challenge":           challenge_b64,
        "iat":                 int(now.timestamp()),
        "exp":                 int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def _decode_token(token: str, *, expected_purpose: str) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.decode(
        token, _jwt_secret(), algorithms=[JWT_ALGORITHM],
    )
    if claims.get("purpose") != expected_purpose:
        raise jwt.InvalidTokenError(
            f"Not a {expected_purpose} token",
        )
    return claims


def allow_credentials_for(
    db: Session, store_id: int, store_employee_id: int,
) -> list[PublicKeyCredentialDescriptor]:
    """Existing credential descriptors for the roster member —
    feeds the browser's ``allowCredentials`` parameter so the OS
    picker only offers the registered authenticator. Empty when
    nothing's registered, which lets the caller surface a
    ``PasskeyNotRegisteredError``."""
    row = passkey_for_employee(db, store_id, store_employee_id)
    if row is None:
        return []
    return [PublicKeyCredentialDescriptor(id=bytes(row.credential_id))]


def emp_handle(store_employee_id: int) -> bytes:
    """User-handle bytes for WebAuthn registration. Uses a
    ``roster:<id>`` prefix to keep the namespace distinct from
    user-side passkeys (which encode ``user.id`` directly)."""
    return f"roster:{store_employee_id}".encode("utf-8")
