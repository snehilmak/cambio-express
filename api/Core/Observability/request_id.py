"""X-Request-ID propagation for the FastAPI / Starlette stack.

Every inbound request either carries an ``X-Request-ID`` header (set
by a load balancer / a previous service in the call chain) or gets a
fresh UUID4 minted. The ID is:

  1. Bound to the structlog contextvars so every log line emitted
     during the request inherits ``request_id=...``.
  2. Stuck on ``request.state.request_id`` so handlers can read it
     without re-parsing headers.
  3. Echoed on the response so the client + downstream services see
     the same value.

That's the whole abstraction. The structlog contextvars binding is
the high-value piece — it makes ``grep request_id=<uuid>`` enough to
reconstruct a request across every SQLAlchemy / stripe / smtp call
inside it.

The Flask-side ``install_request_id(app)`` hook was retired in
PR #550 alongside the Flask app itself.
"""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"


def _resolve_id(incoming: str | None) -> str:
    """Use the inbound header if present and short, else mint UUID4.

    Cap the inbound length so a malicious client can't push a 2 MB
    "id" into our log records.
    """
    if incoming and len(incoming) <= 200:
        return incoming
    return str(uuid.uuid4())


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
