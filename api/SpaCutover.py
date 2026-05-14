"""SPA-cutover redirect resolver — pure function, no framework.

Decides whether a legacy URL like ``/dashboard`` or
``/reports/sales-by-company`` should 301 to its ``/app/*`` SPA
equivalent. Used by both:

* ``asgi.py`` — production. Called after every other dispatch
  branch (FastAPI, SPA shell, PublicRoutes) and before falling
  through to Flask. Anything not handled by another app and not a
  ``/static/*`` asset gets bounced to the SPA.

* ``tests/conftest.py`` — the Flask ``test_client`` doesn't go
  through ``asgi.py``, so the conftest wraps ``flask_app.wsgi_app``
  with a pre-router that calls ``redirect_target`` to honour the
  same 301s the production ASGI dispatcher applies.

The redirect applies to **every HTTP method**, not just GET — the
legacy POST surface has been retired (the SPA POSTs to
``/api/v2/*`` directly) so a stray POST to ``/admin/users/new``
should bounce to the SPA rather than 404.
"""
from __future__ import annotations

import re
from typing import Callable, Optional


# Path prefixes that NEVER redirect — owned directly by another
# app (Starlette + Flask static) or by the ASGI router itself.
# asgi.py routes most of these before we get here; this list is
# the safety net for the Flask test_client bridge in
# tests/conftest.py.
_PASS_THROUGH_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/api/",
    "/app/",
    "/webhooks/",
    "/tv/",
)

# Exact paths owned by other apps (root landing, PWA assets,
# marketing pages, etc.). Same safety-net rationale.
_PASS_THROUGH_EXACT: frozenset[str] = frozenset({
    "/",
    "/privacy",
    "/app",
    "/sw.js",
    "/manifest.webmanifest",
    "/offline",
    "/favicon.ico",
})


# Legacy paths whose SPA equivalent doesn't simply prepend ``/app/``.
# Captures the URL-shape exceptions.
_PATH_REMAP: dict[str, str] = {
    "/admin/settings":               "/app/settings",
    "/bank/transactions":            "/app/bank-transactions",
    "/superadmin/reports/audit-log": "/app/superadmin/audit-log",
}


def _rewrite_reset_password(tail: str, query_string: str) -> Optional[str]:
    """``/reset-password/<token>`` → ``/app/reset-password?token=…``."""
    if tail and "/" not in tail:
        join = "&" if query_string else ""
        return f"/app/reset-password?token={tail}{join}{query_string}"
    return None


def _rewrite_daily(tail: str, _query_string: str) -> Optional[str]:
    """``/daily/<YYYY-MM-DD>`` → ``/app/daily/edit?date=…``."""
    if tail and "/" not in tail and tail != "edit":
        return f"/app/daily/edit?date={tail}"
    return None


def _rewrite_monthly(tail: str, _query_string: str) -> Optional[str]:
    """``/monthly/<year>/<month>`` → ``/app/monthly/edit?year=…&month=…``."""
    parts = tail.split("/")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"/app/monthly/edit?year={parts[0]}&month={parts[1]}"
    return None


_REWRITES: tuple[
    tuple[str, Callable[[str, str], Optional[str]]],
    ...,
] = (
    ("/reset-password/", _rewrite_reset_password),
    ("/daily/",          _rewrite_daily),
    ("/monthly/",        _rewrite_monthly),
)


# Paths ending with one of these extensions are downloads / raw
# assets. We don't bounce them to the SPA — the SPA can't render
# binary file types. Today's only on-Flask downloads are
# /static/*; everything else (CSV exports, etc.) lives on FastAPI
# and authenticates via Bearer JWT. A bare GET to a legacy
# .csv URL with no Flask handler falls through to a 404, which
# matches the pre-cutover behaviour.
_DOWNLOAD_EXT_RE = re.compile(r"\.(csv|zip|pdf|xlsx|ics|txt|json)$")


def redirect_target(
    *, path: str, query_string: str = "",
) -> Optional[str]:
    """Resolve the SPA target URL for ``path`` or return None to pass through.

    Decision order:

      1. Pass-through prefix / exact match → None (no redirect).
      2. Download-extension path → None (Flask's /static/ or 404).
      3. Custom rewrite (``/reset-password/<token>`` etc.) → target URL.
      4. Path-remap table → target URL.
      5. Default → ``/app/<original-path>``.
    """
    if path in _PASS_THROUGH_EXACT:
        return None
    for prefix in _PASS_THROUGH_PREFIXES:
        if path.startswith(prefix):
            return None
    if _DOWNLOAD_EXT_RE.search(path):
        return None

    for prefix, rewriter in _REWRITES:
        if path.startswith(prefix):
            target = rewriter(path[len(prefix):].rstrip("/"), query_string)
            if target is not None:
                return target

    remap = _PATH_REMAP.get(path)
    if remap is not None:
        if query_string:
            return f"{remap}?{query_string}"
        return remap

    target = f"/app{path}" if path.startswith("/") else f"/app/{path}"
    if query_string:
        return f"{target}?{query_string}"
    return target
