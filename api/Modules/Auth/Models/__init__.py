"""Auth — Models.

Five classes own the auth state that isn't on ``User`` itself:

* ``PasswordResetToken`` — short-lived single-use sha256-hashed
                           token for the /forgot-password flow.
* ``RecoveryCode``       — 10 one-time TOTP-recovery codes per user,
                           shown plaintext at enrollment and
                           sha256-hashed in the DB.
* ``Passkey``            — a WebAuthn credential bound to a user
                           (laptop Touch ID, phone, hardware key).
* ``LoginEvent``         — one row per successful login. Drives the
                           DAU/MAU report.
* ``RefreshToken``       — opaque secret, rotating, 14-day TTL.
                           Backs the silent-refresh flow on the SPA
                           so users don't get bounced to /login when
                           a 30-minute access token expires
                           mid-workflow.

Re-exports of ``Store``, ``StoreOwnerLink``, ``User`` (which the
Auth services use heavily) live alongside the canonical definitions
in ``api/Modules/Tenancy/Models``.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, LargeBinary, String,
    UniqueConstraint,
)

from api.Core.Database import Base


class PasswordResetToken(Base):
    """Short-lived, one-time-use token for the self-service password
    reset flow.

    Storing only the sha256 hash of the token (never the raw value)
    means the DB alone isn't enough for an attacker to reset an
    account — they'd need to have intercepted the email too.
    """

    __tablename__ = "password_reset_token"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("user.id"), nullable=False)
    token_hash = Column(String(128), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at    = Column(DateTime, nullable=True)


class RecoveryCode(Base):
    """One-time-use 2FA recovery code for a user.

    Shown in plaintext exactly once at enrollment time; only the
    sha256 hash is persisted. Consumed on use (``used_at`` set) — a
    consumed code stays in the table so we can show the user how
    many remain. Regenerate via the account-security page wipes all
    rows for that user and mints a fresh batch.
    """

    __tablename__ = "recovery_code"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("user.id"), nullable=False)
    code_hash  = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    used_at    = Column(DateTime, nullable=True)
    __table_args__ = (
        UniqueConstraint("user_id", "code_hash",
                          name="uq_recovery_user_code"),
    )


class Passkey(Base):
    """A WebAuthn credential (passkey) registered to a user.

    One user can have many passkeys (laptop Touch ID, phone, hardware
    key). ``credential_id`` is the unique identifier the browser
    presents at login; ``public_key`` is the CBOR-encoded COSE key
    we use to verify assertions. ``sign_count`` is the
    authenticator-reported counter — we accept equal-or-greater
    values and reject resets to protect against cloned
    authenticators. ``name`` is the user-supplied nickname shown in
    the UI.

    A passkey login is treated as MFA-sufficient for every role
    including superadmin — the credential is phishing-resistant and
    device-bound by construction, so requiring TOTP on top would be
    redundant friction without adding security.
    """

    __tablename__ = "passkey"
    id             = Column(Integer, primary_key=True)
    user_id        = Column(Integer, ForeignKey("user.id"), nullable=False)
    # credential_id is up to 1023 bytes per spec; we store the raw
    # bytes so the server-side verifier doesn't have to re-decode on
    # every use.
    credential_id  = Column(LargeBinary, unique=True, nullable=False)
    public_key     = Column(LargeBinary, nullable=False)
    sign_count     = Column(Integer, default=0, nullable=False)
    name           = Column(String(120), default="")
    aaguid         = Column(String(36), default="")
    transports     = Column(String(120), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    last_used_at   = Column(DateTime, nullable=True)


class LoginEvent(Base):
    """One row per successful login. Backs the DAU/MAU report.
    Historic periods before this model ships show no activity —
    data collects forward from now."""

    __tablename__ = "login_event"
    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"),
                      nullable=False, index=True)
    role    = Column(String(20), default="", index=True)
    at      = Column(DateTime, default=datetime.utcnow,
                      nullable=False, index=True)
    method  = Column(String(20), default="")  # password / passkey / totp
    # Covering composite for the DAU/MAU aggregator. The query is
    # `WHERE at BETWEEN ? AND ? GROUP BY date(at)` with
    # `count(distinct user_id)` — leading on `at` lets the planner
    # do a range scan and have `user_id` already in-index for the
    # distinct-count, no heap fetch per row.
    __table_args__ = (
        Index("ix_login_event_at_user", "at", "user_id"),
    )


class RefreshToken(Base):
    """Opaque, rotating, server-side-revocable refresh credential.

    Pairs with the 30-minute ``db_access_token`` JWT to enable
    silent refresh: when an API request 401s from an expired
    access cookie, the SPA hits ``/auth/refresh``, which looks up
    the row keyed by this token's ``jti`` and (if not revoked and
    not expired) rotates it — issues a fresh access token + fresh
    refresh token, revokes the old refresh row, and points
    ``rotated_to_id`` at the successor.

    Why rotate: if the same refresh token is ever presented twice,
    one of those calls is a replay attack (the legitimate user
    rotated past it). The repeated presentation flips ``revoked_at``
    on the successor and ends the chain — a stolen refresh cookie
    burns out at first attempted reuse.

    Why opaque (not a JWT): refresh tokens MUST be revocable
    mid-TTL. A JWT can't be unsigned. An opaque token whose secret
    lives in the DB is revoked by flipping a column.
    """

    __tablename__ = "refresh_token"
    id              = Column(Integer, primary_key=True)
    # 32-byte URL-safe random — 256 bits of entropy.
    jti             = Column(String(64), unique=True, nullable=False, index=True)
    user_id         = Column(Integer, ForeignKey("user.id"),
                              nullable=False, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow,
                              nullable=False)
    expires_at      = Column(DateTime, nullable=False)
    # NULL until the token is revoked (rotation, logout, or
    # replay-detected). Once non-NULL the row is dead — refresh
    # attempts return 401.
    revoked_at      = Column(DateTime, nullable=True)
    # When the token was rotated (revoked + a successor minted),
    # the new row's id goes here. Lets ops trace the chain for
    # forensics if the replay detector flips.
    rotated_to_id   = Column(
        Integer, ForeignKey("refresh_token.id"), nullable=True,
    )


# Re-export Tenancy models so existing
# ``from api.Modules.Auth.Models import Store`` etc. keep working.
from api.Modules.Tenancy.Models import (  # noqa: E402
    Store, StoreOwnerLink, User,
)


__all__ = [
    "LoginEvent", "Passkey", "PasswordResetToken", "RecoveryCode",
    "RefreshToken", "Store", "StoreOwnerLink", "User",
]
