"""Coverage for the cross-cutting observability layer.

Three independent surfaces under test:

  - Sentry init is a no-op when SENTRY_DSN is empty, and activates
    when it isn't (without actually phoning home — we just assert
    the SDK's hub state).
  - structlog emits real structured records, and contextvars bound by
    the request-ID middleware show up on the rendered event.
  - The FastAPI request-ID middleware: (a) generates a UUID when no
    header is present, (b) echoes an inbound header back on the
    response, (c) caps absurdly long inbound IDs.

The Flask-side request-ID hook was retired in PR #550 alongside
the Flask app itself; production now runs through asgi.py with the
FastAPI middleware doing the work for every request.
"""
from __future__ import annotations

import logging
import re

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.Core.Observability import (
    REQUEST_ID_HEADER, RequestIDMiddleware, init_logging, init_sentry,
)
from api.Core.Observability import (
    request_id as request_id_module,
)
from api.Core.Observability import sentry as sentry_module


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch):
    """Reset the module-level `_INITIALISED` flags between tests.

    `init_logging` + `init_sentry` are idempotent in production; for
    tests we need each one to take effect freshly so we can flip
    config and assert.
    """
    monkeypatch.setattr(sentry_module, "_INITIALISED", False)
    # Don't reset the logging singleton — re-running init_logging in a
    # single process re-binds the root handler, which fights with
    # pytest's caplog capture. Keep it initialised once per session.
    yield


# ─── Sentry ──────────────────────────────────────────────────────


def test_init_sentry_skips_when_dsn_empty(monkeypatch):
    """SDK ships in the requirements but stays asleep until a DSN
    is configured. Empty DSN = zero-cost in CI and local dev."""
    from api.Core.Config import settings as global_settings
    monkeypatch.setattr(global_settings, "sentry_dsn", "")
    assert init_sentry() is False


def test_init_sentry_activates_when_dsn_set(monkeypatch):
    """When SENTRY_DSN is non-empty the SDK initialises with our
    integrations registered. We stub `sentry_sdk.init` so no real
    transport thread starts — production wires this up for real."""
    from api.Core.Config import settings as global_settings
    monkeypatch.setattr(
        global_settings, "sentry_dsn", "https://abc@example.invalid/1",
    )
    monkeypatch.setattr(global_settings, "environment", "ci-test")

    init_called: dict = {}

    def fake_init(**kwargs):
        init_called.update(kwargs)

    monkeypatch.setattr(sentry_module.sentry_sdk, "init", fake_init)

    assert init_sentry() is True
    assert init_called["environment"] == "ci-test"
    assert init_called["dsn"] == "https://abc@example.invalid/1"
    integration_names = {
        type(i).__name__ for i in init_called["integrations"]
    }
    assert {"FastApiIntegration", "StarletteIntegration",
            "SqlalchemyIntegration"} <= integration_names
    assert init_called["traces_sample_rate"] == 0.0
    assert init_called["send_default_pii"] is False


# ─── structlog ───────────────────────────────────────────────────


def test_init_logging_routes_stdlib_through_structlog(monkeypatch):
    """A stdlib log call ends up emitting through the structlog
    formatter, so log lines from third-party libraries (SQLAlchemy,
    urllib3, stripe) come out in the same shape as our own emitters.
    """
    init_logging()  # idempotent
    handlers = logging.getLogger().handlers
    assert handlers, "init_logging should install a stream handler"
    # The handler's formatter is a structlog ProcessorFormatter.
    fmt = handlers[0].formatter
    assert isinstance(fmt, structlog.stdlib.ProcessorFormatter)


def test_request_id_contextvars_bind_to_log_records():
    """The FastAPI middleware binds request-scoped fields via
    structlog.contextvars.bind_contextvars; they should show up on
    every log line emitted through the real processor chain.

    We can't use `structlog.testing.capture_logs()` here — it
    short-circuits the processor chain so `merge_contextvars` never
    runs. Instead run the real chain manually against an event_dict.
    """
    init_logging()
    structlog.contextvars.bind_contextvars(request_id="req-abc-123")
    try:
        event_dict = structlog.contextvars.merge_contextvars(
            None, "info", {"event": "transfer.created", "store_id": 42},
        )
        assert event_dict["request_id"] == "req-abc-123"
        assert event_dict["store_id"] == 42
        assert event_dict["event"] == "transfer.created"
    finally:
        structlog.contextvars.clear_contextvars()


def test_clear_contextvars_after_request():
    """After clear_contextvars (called by the FastAPI middleware
    finally-block), the bound field is gone. Critical — without
    this, the next request would inherit stale `request_id=...`
    from whatever ran last on the same worker thread."""
    structlog.contextvars.bind_contextvars(request_id="leaked")
    structlog.contextvars.clear_contextvars()
    event_dict = structlog.contextvars.merge_contextvars(
        None, "info", {"event": "later"},
    )
    assert "request_id" not in event_dict


# ─── Request-ID middleware: FastAPI ──────────────────────────────


def test_fastapi_generates_request_id_when_header_absent():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    def _ping():
        return {"ok": True}

    with TestClient(app) as client:
        resp = client.get("/ping")
    assert resp.status_code == 200
    rid = resp.headers.get(REQUEST_ID_HEADER)
    assert rid is not None
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        rid,
    )


def test_fastapi_echoes_inbound_request_id():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    def _ping():
        return {"ok": True}

    with TestClient(app) as client:
        resp = client.get(
            "/ping", headers={REQUEST_ID_HEADER: "trace-xyz-789"},
        )
    assert resp.headers.get(REQUEST_ID_HEADER) == "trace-xyz-789"


def test_resolve_id_helper_caps_length():
    """Direct unit-test of the cap — the middleware tests above
    confirm the wiring; this guards the boundary."""
    assert request_id_module._resolve_id(None) != ""
    assert request_id_module._resolve_id("") != ""
    assert request_id_module._resolve_id("ok-123") == "ok-123"
    huge = "x" * 1_000
    assert request_id_module._resolve_id(huge) != huge
