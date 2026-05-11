"""structlog + stdlib logging bridge.

Why structlog instead of bare stdlib logging:

  - Key/value pairs are first-class. ``log.info("transfer.created",
    store_id=42, amount=100)`` produces a structured event, not a
    string we'd have to grep-parse in production.

  - Contextvars carry per-request state (request ID, user ID,
    store ID) across function boundaries without threading them
    through every call. The request-ID middleware binds once;
    every log line emitted during that request inherits the field.

  - One JSON-encoder switch in prod, one human-readable encoder in
    dev. Same call sites either way.

We keep stdlib ``logging`` working in parallel because every
third-party library (SQLAlchemy, urllib3, stripe, etc.) uses it.
``structlog.stdlib.ProcessorFormatter`` routes those records through
the same processor chain so they come out in the same JSON / console
shape as our own emitters.
"""
from __future__ import annotations

import logging
import sys

import structlog

from api.Core.Config import settings


_INITIALISED = False


def init_logging() -> None:
    """Configure structlog + the stdlib logging root once.

    Idempotent — re-entrant calls are a no-op. App + worker + Flask
    CLI commands all call this at boot; the second call is silent.
    """
    global _INITIALISED
    if _INITIALISED:
        return

    # Shared processor chain — runs on every log record before the
    # final encoder. Order matters:
    #   1. contextvars merging picks up bound request-scope state
    #      (request_id, user_id, store_id) so the encoder sees them.
    #   2. log level + timestamp annotate the event dict.
    #   3. structured-exception formatter expands exc_info into a
    #      "exception" field with the rendered traceback.
    #   4. format_exc_info copies the exception to "exception" and
    #      removes exc_info so the JSON encoder doesn't choke.
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if settings.log_format.lower() == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    # structlog side — used by anything that calls
    # `structlog.get_logger()`.
    structlog.configure(
        processors=shared_processors
        + [
            # Stdlib bridge — passes the event dict through to the
            # stdlib handler's formatter (configured below). Without
            # this the stdlib handler receives the message but not
            # the structured fields.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # stdlib side — every third-party library uses stdlib logging
    # (SQLAlchemy, stripe, urllib3, …). Reroute their records through
    # the same processor chain so they come out in the same shape.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Replace any existing handlers (Flask's basicConfig adds one) so
    # we don't double-emit. Safe at boot — we're the only configurer
    # at this point.
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # Tame the chattiest libraries by default. Operators can override
    # via env vars at boot time if they need debug noise.
    for noisy in ("sqlalchemy.engine", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _INITIALISED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger.

    Prefer this over ``structlog.get_logger()`` directly so we get
    type-correct hints (it returns the stdlib-bound variant configured
    above). ``name`` is optional and only used for the stdlib
    underlying logger; structlog's key/value rendering doesn't print
    it by default.
    """
    return structlog.get_logger(name)  # type: ignore[return-value]
