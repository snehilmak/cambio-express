"""Boot-time Flask configuration: SECRET_KEY gate, session cookie
hardening, CSRF protection. Called from app.py."""
from __future__ import annotations

import os

from flask import Flask
from flask_wtf.csrf import CSRFProtect


_SECRET_KEY_DEV_FALLBACK = "dinerobook-dev-secret-change-in-prod"


def install_secret_key(app: Flask) -> None:
    """Apply SECRET_KEY. Refuse to boot in prod with the dev fallback —
    session cookies signed with it would be forgeable by anyone
    reading the repo. "Prod" = APP_BASE_URL starts with https://."""
    app.secret_key = (
        os.environ.get("SECRET_KEY", "")
        or _SECRET_KEY_DEV_FALLBACK
    )
    if (
        os.environ.get("APP_BASE_URL", "").startswith("https://")
        and app.secret_key == _SECRET_KEY_DEV_FALLBACK
    ):
        raise RuntimeError(
            "Refusing to boot in prod with the dev-fallback SECRET_KEY. "
            "Set the SECRET_KEY env var in Render → Environment to a "
            "random value (e.g. `python -c 'import secrets; "
            "print(secrets.token_urlsafe(48))'`) and re-deploy."
        )


def warn_default_seed_passwords(app: Flask) -> None:
    """Loud structured-log warning when prod boots with the default
    seed passwords (super2025! / cambio2025!) still in effect."""
    if not os.environ.get("APP_BASE_URL", "").startswith("https://"):
        return
    missing = []
    if not os.environ.get("SUPERADMIN_PASSWORD"):
        missing.append("SUPERADMIN_PASSWORD")
    if not os.environ.get("ADMIN_PASSWORD"):
        missing.append("ADMIN_PASSWORD")
    if missing:
        app.logger.critical(
            "Seed password fallback is active in prod for: "
            "%s. The default values (super2025! / cambio2025!) "
            "are public in the repo. Either set the env vars OR "
            "change the password in the UI immediately on first login.",
            ", ".join(missing),
        )


def install_session(app: Flask) -> bool:
    """HTTPOnly + SameSite=Lax + Secure (prod only). Returns whether
    we're in https-prod mode (used by other config decisions)."""
    is_https_prod = os.environ.get("APP_BASE_URL", "").startswith("https://")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_https_prod
    from datetime import timedelta
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    return is_https_prod


def install_csrf(app: Flask, *, is_https_prod: bool) -> CSRFProtect:
    """CLAUDE.md invariant #16. CSRFProtect rejects POST/PUT/PATCH/DELETE
    without a valid csrf_token. WTF_CSRF_ENABLED=0 kill-switch is used
    by the test conftest."""
    enabled = os.environ.get("WTF_CSRF_ENABLED", "True") not in (
        "0", "false", "False",
    )
    app.config["WTF_CSRF_ENABLED"] = enabled
    app.config["WTF_CSRF_TIME_LIMIT"] = 60 * 60 * 24 * 7
    app.config["WTF_CSRF_SSL_STRICT"] = is_https_prod
    return CSRFProtect(app)
