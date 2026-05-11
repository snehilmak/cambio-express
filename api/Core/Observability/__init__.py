"""Cross-cutting observability — structured logging, Sentry, request-IDs.

Three independent pieces that all initialise once, at process boot:

  - :func:`init_logging` configures structlog + stdlib logging. Output
    is JSON when ``settings.log_format == "json"`` (production) or a
    coloured-console renderer otherwise (dev). Both modes share the
    same processor chain so log fields are consistent regardless of
    encoder.

  - :func:`init_sentry` activates the Sentry SDK with Flask + FastAPI
    + SQLAlchemy + logging integrations. **No-op when**
    ``settings.sentry_dsn`` **is empty** — the SDK is imported but
    never initialised, so CI and local dev pay nothing.

  - :func:`install_request_id` (Flask) and
    :class:`RequestIDMiddleware` (FastAPI) read an inbound
    ``X-Request-ID`` header or mint a fresh UUID, bind it to the
    structlog contextvars for the duration of the request, and echo
    it back on the response. Cross-system traces become one ``grep``
    away.

The public surface is intentionally small — three init functions
plus one middleware class — so wiring into ``app.py`` and
``api/main.py`` is a couple of lines each.
"""
from .logging import get_logger, init_logging
from .request_id import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    install_request_id,
)
from .sentry import init_sentry

__all__ = [
    "REQUEST_ID_HEADER",
    "RequestIDMiddleware",
    "get_logger",
    "init_logging",
    "init_sentry",
    "install_request_id",
]
