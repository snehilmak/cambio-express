"""Flask-Limiter setup. CLAUDE.md "Rate limiting" invariant #15.

Auth + webhook endpoints get bucketed by client IP. Storage is
in-memory by default; prod sets RATELIMIT_STORAGE_URI=redis://...
in render.yaml so the bucket spans workers. Tests set
RATELIMIT_ENABLED=0 so they don't get 429'd by the seeded admin.
"""
from __future__ import annotations

import os

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


_RATELIMIT_STORAGE = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
_LIMITER_ENABLED = (
    os.environ.get("RATELIMIT_ENABLED", "1") not in ("0", "false", "False")
)


def install(app: Flask) -> Limiter:
    """Attach a Flask-Limiter, then apply auth-burst caps to known
    blueprint endpoints. Returns the limiter for legacy callers
    (``from app import limiter``)."""
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],
        storage_uri=_RATELIMIT_STORAGE,
        strategy="fixed-window",
        enabled=_LIMITER_ENABLED,
        headers_enabled=True,
    )

    # POST-only so a logged-out user hitting the GET form repeatedly
    # doesn't burn the credit they need to actually try a password.
    _auth_burst = limiter.limit(
        "10 per minute; 50 per hour",
        methods=["POST"],
    )

    for endpoint in (
        "auth.login",
        "auth.login_store",
        "auth.employee_login_redirect",
        "auth.login_totp",
        "auth.login_totp_recover",
        "auth.login_totp_enroll",
        "auth.passkey_login_begin",
        "auth.passkey_login_finish",
        "auth.passkey_register_begin",
        "auth.passkey_register_finish",
    ):
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = _auth_burst(
                app.view_functions[endpoint],
            )

    return limiter
