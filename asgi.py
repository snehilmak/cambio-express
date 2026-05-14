"""ASGI entrypoint — production + dev parity.

Production runs::

    gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker

Dev mirrors this via the entrypoint module ``run.py`` (or
``uvicorn asgi:asgi_app --reload`` directly). Tests reach the
same routes through ``starlette.testclient.TestClient(asgi_app)``
— ``tests/conftest.py`` wraps that as ``AsgiTestClient``.

Routing
-------
* ``/api/v2/*``      → FastAPI native ASGI (path prefix stripped)
* ``/webhooks/*``    → FastAPI (Stripe + Resend ingest)
* ``/app`` + ``/app/*`` → Starlette SPA app (``api.spa.spa_app``)
* ``/static/*``      → Starlette ``StaticFiles`` on ``./static``
* Public root-mounted routes (``/``, ``/privacy``, ``/sw.js``,
  ``/offline``, ``/tv/*``, ``/api/tv-pair/*``) → ``api.PublicRoutes``
* Anything else      → ``api.SpaCutover`` 301 to ``/app/<original>``
* ``lifespan``       → forwarded to FastAPI so its startup +
  shutdown hooks fire under uvicorn

Flask is gone. The legacy WSGI fallback that used to route to the
Flask app was retired in PR #550; the only thing it served at
the end was ``/static/*``, which is now a Starlette mount above.
"""
from __future__ import annotations

import os

from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from api.main import api_app as _api_app
from api.PublicRoutes import (
    PUBLIC_ROUTE_PATHS as _PUBLIC_PATHS,
    PUBLIC_ROUTE_PREFIXES as _PUBLIC_PREFIXES,
    public_app as _public_app,
)
from api.SpaCutover import redirect_target as _cutover_redirect
from api.spa import spa_app as _spa_app


# Static assets used by the SPA + email templates (brand mark,
# design tokens, favicon, …). Vite bundles the SPA's own assets
# under /app/assets/; this directory holds the cross-cutting ones
# the React shell + the public HTML templates reference directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR = os.path.join(_HERE, "static")
_static_app = StaticFiles(directory=_STATIC_DIR)


async def asgi_app(scope, receive, send):
    """Top-level ASGI router.

    Three scope types matter:

      * ``lifespan`` — uvicorn fires this once at startup and once
        at shutdown. Forward to FastAPI so its lifespan handlers
        (DB init + seed) run.
      * ``http`` — route by path.
      * ``websocket`` — same routing as http; no WebSocket routes
        today but the structure is right for when they're added.
    """
    if scope["type"] == "lifespan":
        await _api_app(scope, receive, send)
        return

    if scope["type"] in ("http", "websocket"):
        path = scope.get("path", "")

        if path == "/api/v2" or path.startswith("/api/v2/"):
            # Strip the mount prefix; FastAPI's routes are declared
            # relative to it. Setting ``root_path`` keeps OpenAPI /
            # docs URLs absolute.
            new_path = path[len("/api/v2"):] or "/"
            new_scope = {**scope, "path": new_path, "root_path": "/api/v2"}
            await _api_app(new_scope, receive, send)
            return

        # Webhook receivers (Stripe + Resend) live on FastAPI too,
        # but the provider URLs are /webhooks/stripe and
        # /webhooks/resend — no /api/v2 prefix.
        if path == "/webhooks" or path.startswith("/webhooks/"):
            await _api_app(scope, receive, send)
            return

        # SPA shell + Vite-built assets — served from frontend/dist
        # by the Starlette app in api/spa.py. Strip the ``/app``
        # prefix before forwarding so routes inside ``spa_app`` are
        # declared relative.
        #
        # Important: do NOT set ``root_path`` here. Starlette's
        # ``StaticFiles`` Mount checks the scope's ``root_path`` and
        # 404s asset requests when it's non-empty (the
        # ``check_config`` path treats the dir as missing). The SPA
        # shell + assets don't need root_path-aware URL generation —
        # the bundle hard-codes /app/assets/... paths via Vite's
        # ``base`` config.
        if path == "/app" or path.startswith("/app/"):
            new_path = path[len("/app"):] or "/"
            new_scope = {**scope, "path": new_path}
            await _spa_app(new_scope, receive, send)
            return

        # Static assets (brand mark, design tokens, favicon, …)
        # served directly from the ./static directory. Strip the
        # ``/static`` prefix so StaticFiles sees relative paths.
        if path == "/static" or path.startswith("/static/"):
            new_path = path[len("/static"):] or "/"
            new_scope = {**scope, "path": new_path}
            await _static_app(new_scope, receive, send)
            return

        # Public root-mounted routes (landing redirect, PWA chrome,
        # TV display, TV pair-code API). No prefix-strip — these
        # routes declare their literal paths.
        if path in _PUBLIC_PATHS or any(
            path.startswith(p) for p in _PUBLIC_PREFIXES
        ):
            await _public_app(scope, receive, send)
            return

        # SPA-cutover: every legacy URL (e.g. /dashboard,
        # /reports/sales-by-company, /admin/users/new) bounces to
        # the /app/* SPA equivalent.
        if scope["type"] == "http":
            qs = scope.get("query_string", b"").decode("latin-1")
            target = _cutover_redirect(path=path, query_string=qs)
            if target is not None:
                response = RedirectResponse(target, status_code=301)
                await response(scope, receive, send)
                return

    # Final fallback: 404 from FastAPI. Anything that reached here
    # didn't match any mount or redirect rule — let FastAPI's
    # exception handler produce a structured JSON response.
    await _api_app(scope, receive, send)
