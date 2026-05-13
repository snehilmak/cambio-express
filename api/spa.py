"""SPA shell + static asset serving (Starlette).

Replaces the legacy ``@app.route("/app/...")`` Flask routes. Three
public endpoints, all under ``/app``:

* ``GET /app``             → 301 to ``/app/`` so React Router's
                              basename resolves correctly.
* ``GET /app/assets/*``    → year-long immutable cache on each
                              Vite-built JS/CSS file (filenames are
                              content-hashed by Vite, so the URL
                              changes on every build).
* ``GET /app/{path:path}`` → ``frontend/dist/index.html`` (the SPA
                              shell). React Router takes over from
                              there; the actual path is ignored
                              server-side. Returns a helpful 503
                              when the Vite build is missing.

Production routing goes through ``asgi.py`` which forwards any
``/app/*`` path to ``spa_app`` (this module) before the Flask
fallback. The test suite goes through the DispatcherMiddleware
mount in ``app.py`` (swapped in by ``tests/conftest.py`` to a
TestClient-backed bridge so Flask's WSGI ``test_client`` can hit
SPA routes during integration tests).
"""
from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles


_HERE = os.path.dirname(os.path.abspath(__file__))
_SPA_DIR = os.path.normpath(os.path.join(_HERE, "..", "frontend", "dist"))
_SPA_ASSETS_DIR = os.path.join(_SPA_DIR, "assets")
_SPA_INDEX = os.path.join(_SPA_DIR, "index.html")


_BUILD_MISSING_HTML = (
    "<!doctype html><meta charset=utf-8><title>SPA not built</title>"
    "<body style='font-family:monospace;padding:2rem'>"
    "<h1>SPA bundle missing</h1>"
    "<p>Expected <code>frontend/dist/index.html</code> to exist.</p>"
    "<p>For local dev: <code>cd frontend &amp;&amp; npm run dev</code> "
    "and visit <code>http://localhost:5173/app/</code>.</p>"
    "<p>For prod: ensure the build step runs "
    "<code>cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</code>.</p>"
    "</body>"
)


async def _spa_shell(request):
    if not os.path.exists(_SPA_INDEX):
        return HTMLResponse(_BUILD_MISSING_HTML, status_code=503)
    return FileResponse(
        _SPA_INDEX,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


class _NormalizeRootPath:
    """Promote an empty path to ``/`` before Starlette routes the
    request. ``DispatcherMiddleware`` (used in tests) and
    ``asgi.py``'s prefix-strip both yield an empty path when the
    original URL was the bare ``/app`` — Starlette refuses to match
    paths that don't start with ``/``, so we normalise here.

    Net effect: ``/app`` and ``/app/`` both serve ``index.html``.
    React Router's basename (``/app``) matches either form, so the
    trailing slash isn't load-bearing the way it was under Flask."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("path") == "":
            scope = {**scope, "path": "/"}
        await self.app(scope, receive, send)


class _ImmutableAssets(StaticFiles):
    """``StaticFiles`` with a year-long immutable Cache-Control on
    every response. Vite content-hashes its emitted filenames so
    the URL itself changes when the underlying bundle changes — a
    long cache is safe and avoids redundant re-fetches on the SPA's
    every page navigation."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        # 404s from StaticFiles also pass through; only add the
        # cache header on a successful file body so a 404 isn't
        # cached for a year.
        if resp.status_code == 200:
            resp.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
            )
        return resp


# Routes are declared **relative** to the ``/app`` mount point. The
# mount lives in two places:
#   * ``asgi.py``  — production routing strips ``/app`` before
#                    forwarding (mirrors how ``/api/v2`` is handled).
#   * ``app.py``   — DispatcherMiddleware mount used by the pytest
#                    suite; Werkzeug strips the prefix automatically.
# Either way, this app sees paths like ``/``, ``/about``,
# ``/assets/index-xyz.js`` — never the full ``/app/...`` path. The
# ``_NormalizeRootPath`` wrapper handles the bare ``/app`` case
# (which yields an empty path) by promoting it to ``/``.
spa_app = _NormalizeRootPath(Starlette(routes=[
    # Order matters: the ``/assets`` mount must precede the catch-all
    # ``/{path:path}`` route, otherwise the latter would intercept
    # asset URLs and return index.html.
    Mount(
        "/assets",
        _ImmutableAssets(directory=_SPA_ASSETS_DIR, check_dir=False),
    ),
    Route("/{path:path}", _spa_shell, methods=["GET"]),
]))
