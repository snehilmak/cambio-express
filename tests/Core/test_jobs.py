"""Tests for the background-job-queue wrapper (BACKLOG D5).

Covers:
* Sync fallback (default) — runs the callable and returns its
  result, errors propagate.
* Sync fallback when only one of the two env vars is set
  (defensive: if a deploy misses ``REDIS_URL``, queuing must NOT
  silently no-op, but the wrapper must still execute the call).
* Queued path — enabled flag flips the wrapper to RQ. Mocked so
  the test suite doesn't need a live Redis.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from api.Core import Jobs


@pytest.fixture(autouse=True)
def _reset_queue_singleton():
    """The wrapper caches its RQ Queue at module scope. Reset it
    around each test so env-var changes are honored."""
    Jobs._queue = None
    yield
    Jobs._queue = None


def _clear_env(monkeypatch):
    monkeypatch.delenv("JOB_QUEUE_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)


# ── Sync fallback ──────────────────────────────────────────────


def test_enqueue_runs_synchronously_by_default(monkeypatch):
    """Out-of-the-box: ``enqueue(fn, ...)`` is a thin alias for
    ``fn(...)``. Returns the function's return value."""
    _clear_env(monkeypatch)

    def double(x: int) -> int:
        return x * 2

    assert Jobs.enqueue(double, 7) == 14


def test_enqueue_propagates_exceptions_in_sync_mode(monkeypatch):
    """Errors must not be swallowed when the wrapper is in sync
    mode — the request handler needs to see them and return a 5xx."""
    _clear_env(monkeypatch)

    def boom() -> None:
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        Jobs.enqueue(boom)


def test_enqueue_keyword_args_in_sync_mode(monkeypatch):
    """Kwargs forward through cleanly."""
    _clear_env(monkeypatch)

    def greet(name: str, *, salutation: str = "Hi") -> str:
        return f"{salutation}, {name}"

    assert Jobs.enqueue(greet, "Ada", salutation="Hello") == "Hello, Ada"


# ── Partial enablement (defensive) ─────────────────────────────


def test_enqueue_flag_alone_without_redis_url_falls_back_to_sync(
    monkeypatch,
):
    """If JOB_QUEUE_ENABLED=1 but REDIS_URL is unset, the wrapper
    must NOT attempt to enqueue (no Redis URL means no Redis).
    Falling back to sync execution keeps the system functional
    while the deploy is fixed."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("JOB_QUEUE_ENABLED", "1")

    calls = []

    def record(x):
        calls.append(x)
        return "ok"

    assert Jobs.enqueue(record, "hello") == "ok"
    assert calls == ["hello"]


def test_enqueue_redis_url_alone_falls_back_to_sync(monkeypatch):
    """Same logic the other way — having REDIS_URL set (e.g. for
    slowapi's rate-limit storage) must not accidentally enable
    job queuing. Only the explicit flag flips behavior."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    calls = []
    Jobs.enqueue(lambda: calls.append(1))
    assert calls == [1]


# ── Queued mode ────────────────────────────────────────────────


def test_enqueue_pushes_to_rq_when_enabled(monkeypatch):
    """With both env vars set, ``enqueue`` calls ``Queue.enqueue``
    and returns ``None`` (the worker will run the job; the caller
    doesn't get its return value)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("JOB_QUEUE_ENABLED", "1")
    monkeypatch.setenv("REDIS_URL", "redis://fakehost:6379/0")

    # Mock both 'redis' and 'rq' so the test doesn't need a real
    # connection — we only care about the wrapper's wiring.
    mock_queue_instance = MagicMock()
    mock_queue_instance.enqueue.return_value = MagicMock(id="job-abc")
    fake_redis_module = MagicMock()
    fake_redis_module.from_url.return_value = MagicMock()
    fake_rq_module = MagicMock()
    fake_rq_module.Queue.return_value = mock_queue_instance

    with patch.dict(os.sys.modules, {
        "redis": fake_redis_module,
        "rq": fake_rq_module,
    }):
        def some_work(uid: int, *, kind: str = "x") -> str:
            return f"{kind}:{uid}"

        result = Jobs.enqueue(some_work, 42, kind="welcome")

    assert result is None
    mock_queue_instance.enqueue.assert_called_once_with(
        some_work, 42, kind="welcome",
    )
    fake_redis_module.from_url.assert_called_once_with(
        "redis://fakehost:6379/0",
    )
