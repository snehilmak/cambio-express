"""ASGI entrypoint for production + dev parity.

Production runs::

    gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker

Dev mirrors this via ``python app.py`` (which now boots uvicorn
pointing at this same module). Tests stay on Flask's
``test_client()`` and use the in-app DispatcherMiddleware (see
``app.py``'s strangler-fig block + ``tests/conftest.py``'s
TestClient bridge); production never traverses that path.

Why we route here instead of using the in-app
DispatcherMiddleware: the inner ``a2wsgi.ASGIMiddleware`` (which
wraps FastAPI for the WSGI-side mount) accumulates leaked
asyncio tasks in its background thread under sustained load.
That crashed gunicorn workers in May 2026 (``CRITICAL WORKER
TIMEOUT`` → ``SIGKILL`` → "Network error" in the SPA login
screen). With this entrypoint, ``/api/v2/*`` runs native ASGI
and the leaky thread is never in the request path.

Routing
-------
* ``/api/v2/*`` → FastAPI native ASGI (path prefix stripped)
* everything else → Flask via ``a2wsgi.WSGIMiddleware`` (the
  WSGI-direction bridge is stateless — no accumulating tasks)
* ``lifespan`` scope → forwarded to the FastAPI app so its
  startup / shutdown hooks fire under uvicorn

We import the FastAPI + Flask apps directly rather than reaching
into ``app.py``'s DispatcherMiddleware mount. The mount is still
configured at import time (for the test suite's Flask
``test_client``), but we don't depend on its shape here — the
tests rewrite it to a plain function, which would break a
mount-shape assertion.
"""
from a2wsgi import WSGIMiddleware

# Importing `app` runs the full module-level init (model
# definitions, FastAPI mount onto app.wsgi_app, seed data, …).
# We don't use the dispatcher itself — production routing happens
# below — but we DO want the side effects (DB init, blueprint
# registration) to fire exactly once at boot.
from app import app as flask_app
from api.main import api_app as _api_app


_flask_asgi = WSGIMiddleware(flask_app.wsgi_app)


async def asgi_app(scope, receive, send):
    """Top-level ASGI router.

    Three scope types matter:

      * ``lifespan`` — uvicorn fires this once at startup and once
        at shutdown. Forward to FastAPI so its lifespan handlers
        (if any) run. Flask has no lifespan hooks; ignoring them
        on the WSGI side is correct.
      * ``http`` — route by path. ``/api/v2/*`` goes to FastAPI
        directly; everything else gets WSGI-bridged into Flask.
      * ``websocket`` — same routing as http; we don't have any
        WebSocket routes today but the structure is right for
        when they're added.
    """
    if scope["type"] == "lifespan":
        await _api_app(scope, receive, send)
        return

    if scope["type"] in ("http", "websocket"):
        path = scope.get("path", "")
        if path == "/api/v2" or path.startswith("/api/v2/"):
            # Strip the mount prefix; FastAPI's routes are declared
            # relative to the mount point. Setting ``root_path``
            # keeps OpenAPI / docs URLs absolute (matches how the
            # legacy dispatcher mount was configured).
            new_path = path[len("/api/v2"):] or "/"
            new_scope = {**scope, "path": new_path, "root_path": "/api/v2"}
            await _api_app(new_scope, receive, send)
            return

    await _flask_asgi(scope, receive, send)
