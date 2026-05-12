"""Smoke tests for the production ASGI entrypoint at `asgi:asgi_app`.

Render runs `gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker`
in prod. The dev `python app.py` path also boots uvicorn pointing at
the same entrypoint so dev matches prod. These tests verify that:

  • /api/v2/* requests route to the FastAPI app **directly** (no
    in-app a2wsgi.ASGIMiddleware bridge — that bridge crashed
    workers under sustained load in May 2026).
  • Everything else routes to the Flask WSGI app via
    a2wsgi.WSGIMiddleware (the SAFE direction of the bridge —
    stateless, no accumulation).
  • Path rewriting drops the /api/v2 prefix before forwarding so
    FastAPI's routes (declared without the prefix) match.

We use httpx + ASGITransport to talk to `asgi_app` without spinning
up a real network listener. Tests are short-lived single-call so
they exercise the entrypoint shape, not its long-term stability —
the latter is what the prod gunicorn deploy actually validates.

The tests are sync wrappers around async httpx calls via
`asyncio.run` to avoid adding pytest-asyncio as a dependency just
for these four cases.
"""
import asyncio


def _run(coro):
    """Sync wrapper for an async coroutine. Each test gets its own
    fresh event loop — important because the lifespan test mutates
    loop state and we don't want it to leak into siblings."""
    return asyncio.new_event_loop().run_until_complete(coro)


def test_asgi_app_routes_api_v2_to_fastapi():
    """A GET to a FastAPI-owned path should reach FastAPI directly.
    `/api/v2/openapi.json` is unauthenticated and always exists, so
    it's the cleanest signal that FastAPI received the request."""
    import httpx
    from asgi import asgi_app

    async def go():
        transport = httpx.ASGITransport(app=asgi_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver",
        ) as ac:
            return await ac.get("/api/v2/openapi.json")

    resp = _run(go())
    assert resp.status_code == 200
    spec = resp.json()
    # Sanity: this is FastAPI's OpenAPI doc, not Flask's 404 page.
    assert "openapi" in spec
    assert "paths" in spec


def test_asgi_app_routes_non_api_to_flask():
    """A GET to a Flask-only path should reach Flask via the WSGI
    bridge. `/privacy` is a known public route that always 200s (or
    301s through the SPA-cutover hook) without auth."""
    import httpx
    from asgi import asgi_app

    async def go():
        transport = httpx.ASGITransport(app=asgi_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver",
        ) as ac:
            return await ac.get("/privacy")

    resp = _run(go())
    # Either the legacy Jinja /privacy 200s, or the SPA-cutover
    # redirect bounces it to /app/privacy. Both prove Flask
    # received the request (FastAPI doesn't know about /privacy).
    assert resp.status_code in (200, 301, 302)


def test_asgi_app_strips_api_v2_prefix():
    """The router must strip the `/api/v2` mount prefix before
    forwarding to FastAPI. If we forgot the strip, FastAPI would
    look for `/api/v2/openapi.json` in its routing table and 404.
    Spelled out here so a future refactor doesn't accidentally
    double-prefix the path."""
    import httpx
    from asgi import asgi_app

    async def go():
        transport = httpx.ASGITransport(app=asgi_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver",
        ) as ac:
            return await ac.get("/api/v2/openapi.json")

    resp = _run(go())
    assert resp.status_code == 200


def test_asgi_lifespan_forwards_to_fastapi():
    """The lifespan scope must reach the FastAPI app so its
    startup / shutdown hooks fire. Without forwarding, uvicorn
    would block on startup waiting for `lifespan.startup.complete`
    that never arrives."""
    from asgi import asgi_app

    state = {"startup": False, "shutdown": False}
    queue = ["lifespan.startup", "lifespan.shutdown"]

    async def receive():
        # Yield messages in order; once exhausted, block forever
        # so the handler can finish naturally on shutdown.
        if queue:
            return {"type": queue.pop(0)}
        await asyncio.sleep(60)
        return {"type": "lifespan.shutdown"}

    async def send(message):
        if message["type"] == "lifespan.startup.complete":
            state["startup"] = True
        elif message["type"] == "lifespan.shutdown.complete":
            state["shutdown"] = True

    async def go():
        scope = {"type": "lifespan"}
        await asyncio.wait_for(
            asgi_app(scope, receive, send), timeout=5.0,
        )

    _run(go())
    assert state["startup"], "FastAPI lifespan startup didn't complete"
    assert state["shutdown"], "FastAPI lifespan shutdown didn't complete"
