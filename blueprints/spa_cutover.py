"""SPA cutover before_request hook — legacy URL → /app/<path> 301.

Permanent redirect from every legacy URL (``/dashboard``,
``/transfers``, ``/admin/audit-log``, …) to the equivalent React SPA
route under ``/app/*``.

The redirect is a generic catch-all: any path that isn't ``/static/``,
``/api/``, ``/app/``, ``/webhooks/``, or a known root surface gets
``/app/<original-path>`` returned with a 301. A handful of paths need
parameter rewriting (e.g. ``/reset-password/<token>`` → query string,
``/daily/<date>`` → ``/daily/edit?date=…``) and live in the
``_REWRITES`` table below.

The redirect applies to **every HTTP method**, not just GET — the
legacy POST surface has been retired (the SPA POSTs to ``/api/v2/*``
directly) so a stray POST to ``/admin/users/new`` should bounce to
the SPA rather than 404.

This is a request-lifecycle hook, not a route surface — uses the
``register(app)`` pattern rather than Flask's ``Blueprint`` class
because Flask Blueprint ``before_request`` hooks only fire for
routes registered in that Blueprint. We need this hook to intercept
*every* legacy URL across the app.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from flask import Flask, Response, current_app, redirect, request
from werkzeug.exceptions import MethodNotAllowed, NotFound


# Paths ending with one of these file extensions are downloads /
# raw assets that the SPA doesn't serve — Flask handles them.
_DOWNLOAD_EXT_RE = re.compile(r"\.(csv|zip|pdf|xlsx|ics|txt|json)$")


# GET paths with a real Flask handler we want to keep wired up.
# Used for state-mutating GETs (impersonation, etc.) and any other
# legacy Flask GET surface that ISN'T rendering dead Jinja chrome.
# Without this list those paths would be 301'd into the SPA and the
# kept handler would never run.
_LEGACY_GET_PASS_THROUGH: tuple[str, ...] = (
    "/superadmin/impersonate/",  # superadmin_extras.py — session GET
)


# Path prefixes that never redirect — owned by Flask directly.
# These are the "live" Flask surfaces that haven't moved to the SPA
# and shouldn't redirect to /app/*: static assets, the FastAPI
# mount, the SPA shell itself, webhook receivers, the TV kiosk
# public display.
_PASS_THROUGH_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/api/",
    "/app/",
    "/webhooks/",
    "/tv/",       # blueprints/tv.py — public kiosk display
    "/tv-pair/",  # blueprints/tv_pair.py — pairing flow
)

# Exact paths owned by Flask (root landing, PWA assets, marketing
# pages, etc.).
_PASS_THROUGH_EXACT: frozenset[str] = frozenset({
    "/",                      # blueprints/landing.py
    "/privacy",               # blueprints/landing.py
    "/app",                   # SPA-shell trailing-slash fixer
    "/sw.js",                 # blueprints/pwa.py
    "/manifest.webmanifest",  # blueprints/pwa.py
    "/offline",               # blueprints/pwa.py
    "/favicon.ico",
})

# Login / logout / signup POSTs need to land on Flask's cookie-session
# handler in `blueprints/auth.py` so the legacy form still works for
# the two pages that haven't fully moved to JWT (chunk 3 retires
# this). The GETs DO redirect to /app/login etc. — only POSTs pass
# through.
# Only /login + /logout + 2FA POSTs still go to Flask — those still
# write to ``session["user_id"]`` and chunk 3 retires them. Everything
# else (signup, forgot-password, reset-password) lives entirely on the
# SPA / FastAPI side, so even POSTs to those legacy paths bounce.
_AUTH_POST_PATHS: frozenset[str] = frozenset({
    "/login",
    "/login/2fa",
    "/login/2fa/enroll",
    "/login/2fa/recover",
    "/logout",
})


# Legacy paths whose SPA equivalent doesn't simply prepend `/app/`.
# Most legacy paths map 1:1 (``/dashboard`` → ``/app/dashboard``);
# this table captures the exceptions where the SPA URL shape
# diverges from the legacy URL shape.
_PATH_REMAP: dict[str, str] = {
    "/admin/settings":               "/app/settings",
    "/bank/transactions":            "/app/bank-transactions",
    "/superadmin/reports/audit-log": "/app/superadmin/audit-log",
}


# Rewrites for legacy URL shapes that don't map 1:1 to /app/<same-path>.
# Each entry is a (prefix, rewriter) — rewriter receives the path tail
# (everything after the prefix) and returns the target ``/app/...``
# URL, or None to skip and fall through to the generic catch-all.
def _rewrite_reset_password(tail: str) -> Optional[str]:
    if tail and "/" not in tail:
        qs = request.query_string.decode("utf-8")
        join = "&" if qs else ""
        return f"/app/reset-password?token={tail}{join}{qs}"
    return None


def _rewrite_daily(tail: str) -> Optional[str]:
    if tail and "/" not in tail and tail != "edit":
        return f"/app/daily/edit?date={tail}"
    return None


def _rewrite_monthly(tail: str) -> Optional[str]:
    parts = tail.split("/")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"/app/monthly/edit?year={parts[0]}&month={parts[1]}"
    return None


_REWRITES: tuple[tuple[str, Callable[[str], Optional[str]]], ...] = (
    ("/reset-password/", _rewrite_reset_password),
    ("/daily/",          _rewrite_daily),
    ("/monthly/",        _rewrite_monthly),
)


def _maybe_spa_redirect() -> Optional[Response]:
    """Flask before_request hook — 301 every legacy URL to /app/<path>.

    Order:

      1. Pass-through list (``/``, ``/static/...``, ``/api/...``,
         ``/app/...``, ``/webhooks/...``, PWA assets) → no redirect.
      2. ``_AUTH_POST_PATHS`` POSTs → pass through to
         ``blueprints/auth.py`` (chunk 3 retires the cookie-session
         path).
      3. Custom rewrites (``/reset-password/<token>`` etc.) → 301
         with query-string surgery.
      4. Path-shape exceptions in ``_PATH_REMAP`` → 301 to the SPA
         equivalent.
      5. Existing Flask handler for a NON-auth, NON-GET method
         (POST/PUT/DELETE/PATCH) → pass through. We let Flask's own
         route table own writes to surfaces like ``/superadmin/
         send-test-email`` (POST handlers we kept) but force GETs
         to bounce to the SPA so the dead Jinja chrome never
         renders.
      6. Default → 301 to ``/app/<original-path>``.
    """
    path = request.path
    method = request.method

    if path in _PASS_THROUGH_EXACT:
        return None
    for prefix in _PASS_THROUGH_PREFIXES:
        if path.startswith(prefix):
            return None
    if method == "POST" and path in _AUTH_POST_PATHS:
        return None

    # Custom rewrites for paths that need query-string surgery.
    for prefix, rewriter in _REWRITES:
        if path.startswith(prefix):
            target = rewriter(path[len(prefix):].rstrip("/"))
            if target is not None:
                return _redirect_with_query(target, preserve_qs=False)
            # Custom rewriter declined; fall through.

    # Path-shape exceptions take precedence over the catch-all.
    remap = _PATH_REMAP.get(path)
    if remap is not None:
        return _redirect_with_query(remap)

    # Non-GET methods to handlers Flask still owns (POSTs to
    # /superadmin/send-test-email, /account/passkeys/<id>/delete,
    # /admin/tax-export, etc.) pass through. GETs of legacy paths
    # always bounce to the SPA so the dead Jinja chrome never
    # renders — even when auth.py still has a GET handler for
    # /login (chunk 3 retires that).
    if method != "GET" and _has_handler(path, method):
        return None
    # File-extension GETs (CSV / ZIP / PDF downloads) flow to
    # Flask's handler if one is registered. The Jinja UI never
    # rendered templates at these paths, so passing them through
    # doesn't risk hitting dead chrome.
    if (
        method == "GET"
        and _DOWNLOAD_EXT_RE.search(path)
        and _has_handler(path, method)
    ):
        return None
    # Explicit GET pass-through for state-mutating Flask surfaces.
    if method == "GET":
        for prefix in _LEGACY_GET_PASS_THROUGH:
            if path.startswith(prefix) and _has_handler(path, method):
                return None

    # 301 to /app/<path> so legacy bookmarks resolve.
    target = f"/app{path}" if path.startswith("/") else f"/app/{path}"
    return _redirect_with_query(target)


def _has_handler(path: str, method: str) -> bool:
    """True when Flask has a registered route for (path, method)."""
    adapter = current_app.url_map.bind("localhost")
    try:
        adapter.match(path, method=method)
        return True
    except MethodNotAllowed:
        # Path exists with a different method — treat as "handled" so
        # we surface a 405 instead of a 301 to the SPA.
        return True
    except NotFound:
        return False
    except Exception:
        # Routing surprised us — fail open and let Flask decide.
        return True


def _redirect_with_query(target: str, *, preserve_qs: bool = True) -> Response:
    qs = request.query_string.decode("utf-8")
    if preserve_qs and qs:
        target = f"{target}?{qs}"
    return redirect(target, code=301)


def register(app: Flask) -> None:
    """Attach the SPA-cutover before_request hook to the given app.

    Idempotent at the import level (the hook closure captures the
    module-level state). Safe to call once at boot from ``app.py``.
    """
    app.before_request(_maybe_spa_redirect)
