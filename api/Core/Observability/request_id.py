"""X-Request-ID propagation for Flask + FastAPI.

Every inbound request either carries an ``X-Request-ID`` header (set
by a load balancer / a previous service in the call chain) or gets a
fresh UUID4 minted. The ID is:

  1. Bound to the structlog contextvars so every log line emitted
     during the request inherits ``request_id=...``.
  2. Stuck on ``flask.g.request_id`` (Flask) or ``request.state.
     request_id`` (FastAPI) so handlers can read it without
     re-parsing headers.
  3. Echoed on the response so the client + downstream services see
     the same value.

That's the whole abstraction. The structlog contextvars binding is
the high-value piece — it makes ``grep request_id=<uuid>`` enough to
reconstruct a request across both halves of the app and every
SQLAlchemy / stripe / smtp call inside it.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask


REQUEST_ID_HEADER = "X-Request-ID"


def _resolve_id(incoming: str | None) -> str:
    """Use the inbound header if present and short, else mint UUID4.

    Cap the inbound length so a malicious client can't push a 2 MB
    "id" into our log records.
    """
    if incoming and len(incoming) <= 200:
        return incoming
    return str(uuid.uuid4())


# ── Flask side ──────────────────────────────────────────────────────


def install_request_id(app: "Flask") -> None:
    """Register before/after-request hooks on a Flask app.

    Safe to call once at boot. Subsequent calls duplicate the hooks;
    don't.
    """
    # Defer the Flask import so this module can be loaded by code
    # paths that don't have Flask available (pure FastAPI workers in
    # the post-cleanup world).
    from flask import g, request

    @app.before_request
    def _bind_request_id() -> None:
        request_id = _resolve_id(request.headers.get(REQUEST_ID_HEADER))
        g.request_id = request_id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.path,
        )

    @app.after_request
    def _echo_request_id(response):  # type: ignore[no-untyped-def]
        # `g.request_id` may be missing if the before-request hook
        # didn't run (e.g. error during routing). Fall back to the
        # raw header so we always echo *something*.
        request_id = getattr(g, "request_id", None) or request.headers.get(
            REQUEST_ID_HEADER,
        )
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.teardown_request
    def _clear_contextvars(_exc):  # type: ignore[no-untyped-def]
        # Important — contextvars persist across the worker thread
        # otherwise, and the next request would inherit stale fields.
        structlog.contextvars.clear_contextvars()


# ── FastAPI side ────────────────────────────────────────────────────


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI equivalent of the Flask hooks above.

    Install with ``app.add_middleware(RequestIDMiddleware)``. Reads
    the inbound header, binds contextvars, attaches to
    ``request.state``, echoes on the response, clears contextvars on
    teardown.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _resolve_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
