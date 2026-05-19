"""Background job queue (BACKLOG D5).

Every Stripe webhook, email send, ACH retry, and retention purge
currently runs synchronously inside the HTTP request that
triggered it. That couples request latency to third-party RTTs
(Stripe API, SMTP), and a slow / failing downstream blocks the
client's connection for the full timeout window.

This module is the plumbing for moving that work off the request
path. The shape is intentionally **boring**:

* When ``JOB_QUEUE_ENABLED=1`` and ``REDIS_URL`` is set, calls to
  :func:`enqueue` push a job onto an RQ queue. A separate worker
  process (declared in ``render.yaml`` once the first call site
  migrates) drains the queue.
* When the flag is unset (the default), :func:`enqueue` runs the
  callable synchronously and returns its result. This keeps:

  - The test suite running without Redis.
  - The default ``uvicorn`` dev loop simple.
  - Existing call sites' semantics unchanged during migration.

The wrapper is intentionally not a hard dependency on RQ — if the
``rq`` import fails (e.g. on a slim runtime image), the sync
fallback still works. Production should fail loudly if
``JOB_QUEUE_ENABLED=1`` but ``rq`` isn't installed; that's a
configuration error, not a graceful degradation.

Usage
-----

    from api.Core.Jobs import enqueue

    def send_welcome_email(user_id: int) -> None:
        # Heavy: SMTP round-trip + 3 DB queries + an audit insert.
        ...

    # In a route handler:
    enqueue(send_welcome_email, user.id)

After the worker drains the queue, the email is sent. Caller
returns to the client immediately.

For now nothing in the codebase imports this module — the first
migration (probably ``customer.subscription.deleted`` webhook,
which fans out to retention update + email send + audit insert)
lands in a follow-up commit. The infrastructure ships first so
migration commits stay small.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _queue_enabled() -> bool:
    """True when callers should defer work to the worker.

    Two env vars must both be set so we can't accidentally enable
    queuing without a Redis URL pointing somewhere real:
    ``JOB_QUEUE_ENABLED=1`` flips the feature, ``REDIS_URL``
    provides the connection. Either missing means sync mode.
    """
    return (
        os.environ.get("JOB_QUEUE_ENABLED") == "1"
        and bool(os.environ.get("REDIS_URL"))
    )


# RQ + Redis are optional at import time so ``api`` modules can
# import this wrapper without paying the dep cost on test boots.
# Resolution happens lazily inside :func:`_get_queue`.
_queue = None


def _get_queue() -> Any:
    """Lazily construct + cache the RQ Queue. Raises if the queue
    is enabled but ``rq`` / ``redis`` aren't importable, since
    that's a misconfiguration."""
    global _queue
    if _queue is not None:
        return _queue
    try:
        import redis
        from rq import Queue
    except ImportError as exc:  # pragma: no cover - exercised in prod-shape
        raise RuntimeError(
            "JOB_QUEUE_ENABLED=1 but 'rq' / 'redis' packages "
            "aren't installed. Add them to requirements.txt or "
            "unset JOB_QUEUE_ENABLED.",
        ) from exc
    redis_url = os.environ["REDIS_URL"]
    conn = redis.from_url(redis_url)  # type: ignore[no-untyped-call]
    _queue = Queue("default", connection=conn)
    return _queue


def enqueue(
    fn: Callable[..., T], *args: Any, **kwargs: Any,
) -> T | None:
    """Run ``fn(*args, **kwargs)`` in the background when queuing
    is enabled, or synchronously otherwise.

    * **Sync mode** (the default): returns ``fn(*args, **kwargs)``.
      Errors propagate to the caller — same as a direct call.

    * **Async mode**: pushes the call onto Redis and returns
      ``None``. The worker process picks it up and runs it. Errors
      surface in the worker log, not the request that enqueued.

    Caveat: jobs serialise their args through RQ's pickler. Pass
    primitives (ids, dicts, lists) — not ORM objects (they
    reference a Session that's closed by the time the worker
    runs).
    """
    if not _queue_enabled():
        logger.debug(
            "enqueue (sync): %s args=%s kwargs=%s",
            getattr(fn, "__qualname__", fn),
            args, kwargs,
        )
        return fn(*args, **kwargs)
    q = _get_queue()
    job = q.enqueue(fn, *args, **kwargs)
    logger.info(
        "enqueue (queued): job_id=%s %s args=%s",
        job.id, getattr(fn, "__qualname__", fn), args,
    )
    return None


__all__ = ["enqueue"]
