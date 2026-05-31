"""Audit logging helpers — claims-aware wrappers around the
``record_operator_action`` / ``record_superadmin_action`` Services.

The underlying recorders take explicit identity kwargs (user_id,
user_name, user_role, store_id) because they're context-free.
Every controller that needs to log used to inline the same
``claims["sub"]`` / ``claims["username"]`` / ``claims["role"]``
extraction — that's 60+ duplicated call sites.

This module provides two thin facades that pull identity out of
JWT claims (FastAPI's standard request principal) so a controller
just writes::

    audit_operator(
        db, claims,
        action="update_store_info",
        target_type="store",
        target_id=str(store.id),
        target_label=store.name,
        summary=f"changed: {', '.join(fields)}",
    )

For superadmin endpoints with a resolved ``User`` row::

    audit_superadmin(
        db, sa_user,
        action="extend_trial",
        target_type="store",
        target_id=str(store.id),
        details=f"+{days} days",
    )

The decorator form ``@audit_action(...)`` is for endpoints where
the audit args are static (no per-row labels needed).

CLAUDE.md invariant #7: every superadmin mutation MUST call
record_audit. Every per-store mutation should too. Using these
helpers consistently makes it harder to forget.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from sqlalchemy.orm import Session

from api.Modules.Audit.Models import OperatorAuditLog, SuperadminAuditLog
from api.Modules.Audit.Services.recorder import (
    record_operator_action,
    record_superadmin_action,
)

F = TypeVar("F", bound=Callable[..., Any])


def audit_operator(
    db: Session,
    claims: dict[str, Any],
    *,
    action: str,
    target_type: str,
    target_id: str = "",
    target_label: str = "",
    summary: str = "",
    store_id: int | None = None,
) -> OperatorAuditLog:
    """Record a per-store operator action, deriving user identity
    from the JWT claims dict.

    Pulls ``user_id``, ``user_name``, ``user_role``, and
    ``store_id`` out of ``claims`` — falls through to the
    explicit ``store_id`` kwarg when not in claims (owners who
    operate cross-store).

    Caller still owns the commit — the audit row is added to the
    session but not flushed, so it rolls back with the mutation
    that triggered it.
    """
    sid = int(store_id if store_id is not None
              else (claims.get("store_id") or 0))
    sub = claims.get("sub")
    return record_operator_action(
        db,
        store_id=sid,
        user_id=int(sub) if sub else None,
        user_name=str(
            claims.get("username") or claims.get("full_name") or "",
        ),
        user_role=str(claims.get("role") or ""),
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        action=action,
        summary=summary,
    )


def audit_superadmin(
    db: Session,
    user: Any,
    *,
    action: str,
    target_type: str = "",
    target_id: str = "",
    details: str = "",
) -> SuperadminAuditLog:
    """Record a superadmin action, sourcing identity from the
    resolved ``User`` row (already loaded for permission gating).

    Use this for superadmin mutation endpoints. Returns the
    unsaved row so callers that need the id can flush themselves.
    """
    return record_superadmin_action(
        db,
        admin_id=user.id,
        admin_name=user.full_name or user.username or "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )


def audit_action(
    *,
    action: str,
    target_type: str,
    summary: str | Callable[..., str] = "",
    scope: str = "operator",
) -> Callable[[F], F]:
    """Decorator that records an audit row after the wrapped
    endpoint returns successfully. The route handler receives
    ``db`` + ``claims`` (or ``user``) like usual; on a non-error
    return, the audit row is written and committed alongside
    whatever the endpoint already committed.

    ``summary`` can be a literal string or a callable that
    receives the same kwargs the route handler was called with
    (so you can interpolate field names or row ids dynamically).

    ``scope='operator'`` → calls ``audit_operator()`` (needs
        ``claims`` kwarg in the wrapped function signature).
    ``scope='superadmin'`` → calls ``audit_superadmin()`` (needs
        ``user`` kwarg, typically resolved via
        ``resolve_superadmin_user``).

    For endpoints where the audit details depend on what the
    handler computed (e.g., "changed: name, email"), call
    ``audit_operator()`` directly instead — the decorator is for
    the simple constant-args case.
    """
    if scope not in ("operator", "superadmin"):
        raise ValueError(f"scope must be 'operator' or 'superadmin', got {scope!r}")

    def decorator(fn: F) -> F:
        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            _write_audit(scope, action, target_type, summary, kwargs)
            return result

        @wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fn(*args, **kwargs)
            _write_audit(scope, action, target_type, summary, kwargs)
            return result

        import asyncio
        if asyncio.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _write_audit(
    scope: str,
    action: str,
    target_type: str,
    summary: str | Callable[..., str],
    kwargs: dict[str, Any],
) -> None:
    """Internal — build the audit row from the captured kwargs."""
    db = kwargs.get("db")
    if db is None:
        return
    summary_str = summary(**kwargs) if callable(summary) else summary
    if scope == "operator":
        claims = kwargs.get("claims") or {}
        audit_operator(
            db, claims,
            action=action,
            target_type=target_type,
            summary=summary_str,
        )
    else:
        user = kwargs.get("user") or kwargs.get("sa") or kwargs.get("sa_user")
        if user is None:
            return
        audit_superadmin(
            db, user,
            action=action,
            target_type=target_type,
            details=summary_str,
        )
    db.commit()
