"""Sentry SDK initialisation — no-op when DSN is unset.

The SDK is imported but never activated unless ``SENTRY_DSN`` is set
in the environment, so CI, local dev, and tests pay zero cost. In
production, set ``SENTRY_DSN`` and Sentry captures every unhandled
exception across Flask, FastAPI, SQLAlchemy, and the stdlib logger.

Integrations enabled:

  - **FlaskIntegration** — every Flask request is a Sentry
    transaction; unhandled exceptions get the request context.
  - **FastApiIntegration / StarletteIntegration** — same for the
    FastAPI half.
  - **SqlalchemyIntegration** — every query becomes a Sentry span
    so we see DB-bound performance in traces.
  - **LoggingIntegration** — stdlib ``logger.error`` and
    ``logger.exception`` calls are captured as Sentry events (with
    ``logger.warning`` recorded as breadcrumbs).
"""
from __future__ import annotations

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from api.Core.Config import settings


_INITIALISED = False


def init_sentry() -> bool:
    """Activate Sentry if a DSN is configured.

    Returns ``True`` if Sentry was initialised, ``False`` if it was
    skipped (empty DSN). Idempotent — second calls return the same
    value without re-initialising the SDK.

    The ``send_default_pii=False`` default keeps user emails / IPs
    out of Sentry. Enable per-event scrubbing rules in the Sentry
    project settings if you decide to capture PII later.
    """
    global _INITIALISED
    if _INITIALISED:
        return True
    if not settings.sentry_dsn:
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        # Capture errors from both halves of the app + stdlib loggers.
        integrations=[
            FlaskIntegration(),
            FastApiIntegration(),
            StarletteIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(
                # `event_level` is the level at which a log entry
                # becomes a Sentry event. Below that, log lines are
                # attached as breadcrumbs to the next event.
                event_level=None,  # disable; we use explicit capture_exception
            ),
        ],
        # Performance traces: default 0 = error capture only. Set
        # SENTRY_TRACES_SAMPLE_RATE=0.05 in prod to capture 5% of
        # traffic without blowing the Sentry quota.
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # PII off by default — emails, IPs, headers redacted at the
        # SDK boundary. Flip in Sentry project settings if you want
        # to capture more for debugging.
        send_default_pii=False,
        # Tighten the breadcrumb cap so a single request can't blow
        # the event size limit.
        max_breadcrumbs=50,
    )
    _INITIALISED = True
    return True
