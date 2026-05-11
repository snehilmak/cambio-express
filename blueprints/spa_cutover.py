"""SPA cutover before_request hook — legacy GET → /app/<slug> 301.

Extracted from ``app.py`` as part of the D2 Blueprint split. This
is a request-lifecycle hook, not a route surface — uses the
``register(app)`` pattern (like ``blueprints/errors.py``) rather
than Flask's ``Blueprint`` class, because:

  * Flask Blueprint ``before_request`` hooks only fire for routes
    registered in that Blueprint. We need this hook to intercept
    GETs of *every* legacy Jinja URL.
  * The hook reads request state but doesn't define endpoints.

What this does
--------------
When ``SPA_CUTOVER_ENABLED=1``, every GET of a legacy Jinja URL
(``/dashboard``, ``/transfers``, ``/reports``, …) returns a 301 to
the equivalent React SPA route under ``/app/*``. POST/PUT/DELETE
fall through to the legacy handlers so an in-flight form submit on
a cached page completes correctly.

Two route shapes:

  * **Static path map** — exact match in ``_SPA_REDIRECT_MAP_STATIC``.
  * **Dynamic patterns** — `/reset-password/<token>`,
    `/transfers/<id>`, `/transfers/<id>/edit`, `/batches/<id>/edit`,
    `/daily/<date>`, `/monthly/<year>/<month>`. Matched by prefix
    + simple parsing.

The default is ``OFF`` (per the production-rollback note in the
original code). Operators flip ``SPA_CUTOVER_ENABLED=1`` per the
cutover plan once the WSGI-wraps-ASGI bottleneck is retired.
"""
from __future__ import annotations

import os
from typing import Optional

from flask import Flask, Response, redirect, request


# Defaults to OFF — the strangler-fig migration is mid-flight, and
# a deploy in May 2026 surfaced a real perf regression when the
# redirect was on by default (the FastAPI-via-WSGI bridge choked
# under prod traffic, slowing logins to "network error" timeouts).
# With the flag off, legacy `/login`, `/dashboard`, etc. keep
# serving the Jinja UI directly with no bridge hop. Flip to "1" on
# Render once the WSGI-wraps-ASGI bottleneck is retired
# (BACKLOG.md P1 #7) or once any one store has been pilot-flipped
# without regression.
SPA_CUTOVER_ENABLED = os.environ.get("SPA_CUTOVER_ENABLED", "0") == "1"


# Static path → SPA path. These are pages that have full SPA parity
# today; everything else falls through to legacy Jinja.
_SPA_REDIRECT_MAP_STATIC: dict[str, str] = {
    "/login":                "/app/login",
    "/signup":               "/app/signup",
    "/forgot-password":      "/app/forgot-password",
    "/privacy":              "/app/privacy",
    "/dashboard":            "/app/dashboard",
    "/transfers":            "/app/transfers",
    "/transfers/new":        "/app/transfers/new",
    "/daily":                "/app/daily",
    "/reports":              "/app/reports",
    "/batches":              "/app/batches",
    "/batches/new":          "/app/batches/new",
    "/monthly":              "/app/monthly",
    "/return-checks":        "/app/return-checks",
    "/owner/locations":      "/app/owner/locations",
    "/owner/pl-rollup":      "/app/owner/pl-rollup",
    "/superadmin/stores":    "/app/superadmin/stores",
    "/superadmin/stores/new": "/app/superadmin/stores/new",
    "/superadmin/reports/audit-log": "/app/superadmin/audit-log",
    "/admin/settings":       "/app/settings",
    "/admin/users":          "/app/admin/users",
    "/admin/users/new":      "/app/admin/users/new",
    "/bank/transactions":    "/app/bank-transactions",
    # SPA-34: Stripe pricing page now on SPA. Note that
    # /admin/subscription stays on legacy because it's a richer
    # page (add-ons + retention info); the SPA settings page only
    # exposes Subscribe + Manage-portal CTAs today.
    "/subscribe":            "/app/subscribe",
    # SPA-37: announcements live under the Platform nav group.
    # The legacy /superadmin/controls?tab=announcements URL has a
    # query param so the static-map can't catch it; that goes
    # through the legacy Jinja for now.
}


def _redirect_with_query(target: str) -> Response:
    qs = request.query_string.decode("utf-8")
    return redirect(f"{target}?{qs}" if qs else target)


def _maybe_spa_redirect() -> Optional[Response]:
    """Flask before_request hook: rewrite GETs of legacy pages to
    their SPA equivalent. POST and other write methods are left
    alone so legacy form submits still complete; the SPA forms POST
    to ``/api/v2/*`` directly so the legacy POST handlers are dead
    paths once the SPA owns the rendering."""
    if not SPA_CUTOVER_ENABLED:
        return None
    if request.method != "GET":
        return None
    path = request.path
    # Static, API, webhooks, and the SPA itself never redirect.
    if (
        path.startswith("/static/")
        or path.startswith("/api/")
        or path.startswith("/app/")
        or path.startswith("/webhooks/")
    ):
        return None

    target = _SPA_REDIRECT_MAP_STATIC.get(path)
    if target is not None:
        return _redirect_with_query(target)

    # Dynamic patterns that need parsing go here.
    # /reset-password/<token>: legacy is path-param, SPA reads
    # ?token=… query param.
    if path.startswith("/reset-password/"):
        tok = path[len("/reset-password/"):]
        if tok and "/" not in tok:
            qs = request.query_string.decode("utf-8")
            join = "&" if qs else ""
            return redirect(f"/app/reset-password?token={tok}{join}{qs}")
    # /transfers/<int>/<edit?>
    if path.startswith("/transfers/"):
        tail = path[len("/transfers/"):].rstrip("/")
        parts = tail.split("/")
        if parts and parts[0].isdigit():
            tid = parts[0]
            if len(parts) == 1:
                return _redirect_with_query(f"/app/transfers/{tid}")
            if len(parts) == 2 and parts[1] == "edit":
                return _redirect_with_query(f"/app/transfers/{tid}/edit")
    # /batches/<int>/edit
    if path.startswith("/batches/"):
        tail = path[len("/batches/"):].rstrip("/")
        parts = tail.split("/")
        if (
            len(parts) == 2 and parts[0].isdigit() and parts[1] == "edit"
        ):
            return _redirect_with_query(f"/app/batches/{parts[0]}/edit")
    # /daily/<date> — legacy uses ?date= now via /daily/edit; map
    # every dated path to /app/daily/edit?date=...
    if path.startswith("/daily/"):
        tail = path[len("/daily/"):].rstrip("/")
        if tail and "/" not in tail:
            return redirect(f"/app/daily/edit?date={tail}")
    # /monthly/<year>/<month>
    if path.startswith("/monthly/"):
        parts = path[len("/monthly/"):].rstrip("/").split("/")
        if (
            len(parts) == 2 and parts[0].isdigit()
            and parts[1].isdigit()
        ):
            return redirect(
                f"/app/monthly/edit?year={parts[0]}&month={parts[1]}"
            )
    return None


def register(app: Flask) -> None:
    """Attach the SPA-cutover before_request hook to the given app.

    Idempotent at the import level (the hook closure captures the
    module-level state). Safe to call once at boot from ``app.py``.
    """
    app.before_request(_maybe_spa_redirect)
