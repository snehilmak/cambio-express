"""Boot-time Flask configuration: SECRET_KEY gate + seed-password
warning. Called from app.py."""
from __future__ import annotations

import os

from flask import Flask


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
