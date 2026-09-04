"""Server-side subscription enforcement (W-1).

Before this, the trial was enforced by the SPA *choosing* to render
a re-subscribe screen: ``store_gate_status`` was called from exactly
one endpoint, the shell payload. A store 30 days past its trial and
26 days past its grace window could still log in, read everything,
and — verified — POST new rows. The business model was sitting on a
client-side check.

This middleware is the server half. It is middleware rather than a
per-route dependency on purpose: middleware is default-deny by
construction, so a write endpoint added next month is covered
without anyone remembering to decorate it. A dependency only ever
protects the routes someone thought to annotate, and the one that
gets forgotten is the one that matters.

The posture, in order:

* **Trial active** (through day 7) — everything works.
* **Grace** (the 4 days after) — **writes are refused, reads still
  work.** The operator can see and export every number they
  entered, and cannot add more. Locking someone out of their own
  books the morning after a trial lapses earns a support ticket and
  a bad review; letting them keep entering data for free earns
  neither.
* **Expired / frozen** — writes stay refused; the SPA gates the UI
  to the re-subscribe screen.

Reads are never blocked here. Their data is retained for 180 days
by design (Billing retention), so refusing to show it back to them
would contradict the product's own promise, and blocking GETs would
break the gate screen's ability to render at all.
"""
from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Methods that never change anything. Everything else is a write.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Path prefixes that stay writable no matter what the subscription
# says. Getting this list wrong in the tight direction is what locks
# someone out of paying you.
#
# Matched against the FastAPI-relative path. asgi.py strips the
# /api/v2 mount prefix before forwarding (see its module docstring),
# so routes here are "/admin/roles", never "/api/v2/admin/roles".
WRITE_EXEMPT_PREFIXES: tuple[str, ...] = (
    # Sign in, sign out, refresh, password reset. A lapsed operator
    # must still be able to reach their account.
    "/auth/",
    # The whole point: let them pay. Checkout, portal, plan changes.
    "/billing/",
    "/subscribe",
    # Provider callbacks carry a signature, not a JWT — they would
    # not resolve a store here anyway, but be explicit.
    "/webhooks/",
    # Support: someone locked out needs to be able to say so.
    "/tickets",
    # Platform staff operate the platform, not a store. Their own
    # role check already gates these.
    "/superadmin/",
)

GATE_MESSAGE_GRACE = (
    "Your free trial has ended. You can still view and export "
    "everything you entered — subscribe to start adding new data "
    "again."
)
GATE_MESSAGE_EXPIRED = (
    "This store's subscription has lapsed. Subscribe to start "
    "using DineroBook again — your data is safe."
)
GATE_MESSAGE_FROZEN = (
    "This store has been suspended. Contact support to restore "
    "access."
)


def _is_write_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in WRITE_EXEMPT_PREFIXES)


def write_block_reason(store: Any) -> tuple[str, str] | None:
    """``(reason, message)`` when this store may not write, else None.

    Pure, and separately testable from the HTTP plumbing.
    """
    if store is None:
        # No store scope — superadmin, or an owner between stores.
        # They are not on a store's subscription.
        return None
    if getattr(store, "frozen_at", None) is not None:
        return "frozen", GATE_MESSAGE_FROZEN
    from api.Modules.Billing.Services.trial import get_trial_status

    status = get_trial_status(store)
    if status == "grace":
        return "trial_ended", GATE_MESSAGE_GRACE
    if status == "expired":
        return "subscription", GATE_MESSAGE_EXPIRED
    return None


class SubscriptionGateMiddleware(BaseHTTPMiddleware):
    """Refuse writes from stores whose subscription has lapsed.

    Deliberately fails OPEN on anything it cannot resolve — a
    malformed token, a missing store, a decode error. Those are the
    auth layer's job to reject with a 401, and a billing gate that
    starts inventing its own auth failures is worse than one that
    lets an already-authenticated edge case through.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.method in SAFE_METHODS:
            return await call_next(request)

        # asgi.py has already stripped /api/v2, so this path is
        # relative — "/admin/roles". Matching the mounted prefix here
        # would silently never fire.
        path = request.url.path
        if _is_write_exempt(path):
            return await call_next(request)

        store = self._resolve_store(request)
        blocked = write_block_reason(store)
        if blocked is None:
            return await call_next(request)

        reason, message = blocked
        # 402 Payment Required: the one status code that says exactly
        # this. A 403 would read as a permissions problem and send
        # the operator hunting through their own access settings.
        return JSONResponse(
            status_code=402,
            content={"detail": message, "reason": reason},
        )

    def _resolve_store(self, request: Request) -> Any:
        """The caller's store, or None when it cannot be determined.

        Every failure path returns None (fail open) — see the class
        docstring.
        """
        try:
            from api.Modules.Auth.Services.jwt_issuer import (
                decode_access_token,
            )
        except Exception:
            return None

        token = None
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip() or None
        if token is None:
            token = request.cookies.get("db_access_token") or None
        if token is None:
            return None

        try:
            claims = decode_access_token(token)
        except Exception:
            return None

        store_id = claims.get("store_id")
        if store_id is None:
            return None

        try:
            from api.Core.Database import SessionLocal
            from api.Modules.Tenancy.Models import Store
        except Exception:
            return None

        session = SessionLocal()
        try:
            return session.get(Store, int(store_id))
        except Exception:
            return None
        finally:
            session.close()


__all__ = [
    "GATE_MESSAGE_EXPIRED", "GATE_MESSAGE_FROZEN", "GATE_MESSAGE_GRACE",
    "SAFE_METHODS", "SubscriptionGateMiddleware", "WRITE_EXEMPT_PREFIXES",
    "write_block_reason",
]
