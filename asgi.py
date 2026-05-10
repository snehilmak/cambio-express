"""ASGI entrypoint for production — bypass the leaky a2wsgi.ASGIMiddleware bridge.

Production was hitting `[CRITICAL] WORKER TIMEOUT` on /api/v2/*
requests because the inner a2wsgi.ASGIMiddleware (mounted at
/api/v2 via Werkzeug's DispatcherMiddleware) accumulates leaked
asyncio tasks in its background thread. Over time the loop's
`run_coroutine_threadsafe(...).result()` calls block forever
(see the gunicorn-worker traceback in the incident logs:
`a2wsgi/asgi.py:214 → concurrent/futures/_base.py:451 → waiter.acquire()`).

This entrypoint switches production from gunicorn-WSGI to
gunicorn-with-UvicornWorker AND routes /api/v2/* to the FastAPI
app **directly at the ASGI layer**, bypassing the inner
a2wsgi.ASGIMiddleware that the legacy Flask DispatcherMiddleware
chain set up. The leaky background thread is no longer in the
request path.

Routing:
  /api/v2/*  → FastAPI native ASGI
  everything else → Flask via a2wsgi.WSGIMiddleware (anyio
                    threadpool — stateless, no accumulation)

The lifespan event is forwarded to the FastAPI app so its
startup / shutdown hooks fire correctly under uvicorn.

Render config (render.yaml) calls this via:

    gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker
"""
from a2wsgi import WSGIMiddleware
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Important: importing `app` runs the full module-level init
# (model definitions, FastAPI mount, seed data, …). The /api/v2
# DispatcherMiddleware is set up here too — we strip it back out
# below so that path doesn't go through the leaky bridge.
from app import app as flask_app


# Pull out the bare Flask WSGI app (pre-DispatcherMiddleware) and
# the raw FastAPI ASGI app. After this we never call into the
# inner a2wsgi.ASGIMiddleware — that's the whole point.
assert isinstance(flask_app.wsgi_app, DispatcherMiddleware), (
    "asgi.py expects app.wsgi_app to be DispatcherMiddleware "
    "(set up by the FastAPI mount block at the bottom of app.py)."
)
_dispatcher = flask_app.wsgi_app
_flask_bare_wsgi = _dispatcher.app  # the original Flask WSGI app
# DispatcherMiddleware mounts: {"/api/v2": ASGIMiddleware(api_app)}.
# ASGIMiddleware stores the wrapped ASGI app as `.app`, so we get
# the bare FastAPI app back.
_api_app = _dispatcher.mounts["/api/v2"].app

_flask_asgi = WSGIMiddleware(_flask_bare_wsgi)


async def asgi_app(scope, receive, send):
    """Top-level ASGI router.

    Three scope types matter:

      * "lifespan" — uvicorn fires this once at startup and once at
        shutdown. Forward to the FastAPI app so its lifespan
        handlers (if any) run. Flask has no lifespan hooks; ignoring
        them on the WSGI side is correct.
      * "http" — route by path. /api/v2/* goes to FastAPI directly;
        everything else gets WSGI-bridged into Flask.
      * "websocket" — same routing as http; we don't have any
        WebSocket routes today but the structure is right for when
        they're added.
    """
    if scope["type"] == "lifespan":
        await _api_app(scope, receive, send)
        return

    if scope["type"] in ("http", "websocket"):
        path = scope.get("path", "")
        if path == "/api/v2" or path.startswith("/api/v2/"):
            # Strip the mount prefix; FastAPI's routes are declared
            # relative to the mount point. Setting `root_path` keeps
            # OpenAPI / docs URLs absolute (matches how the legacy
            # dispatcher mount was configured).
            new_path = path[len("/api/v2"):] or "/"
            new_scope = {**scope, "path": new_path, "root_path": "/api/v2"}
            await _api_app(new_scope, receive, send)
            return

    await _flask_asgi(scope, receive, send)
