"""Billing module — Controllers (FastAPI router).

Mounts at `/api/v2/billing/*`. Two endpoints today:

  POST /billing/checkout → mint a Stripe Checkout Session for the
       chosen plan, return its hosted URL. SPA redirects.
  POST /billing/portal   → mint a Stripe Billing Portal Session,
       return its hosted URL. SPA redirects.

Both endpoints delegate to the existing Billing Services
(`create_checkout_session`, `create_billing_portal_session`)
which already encapsulate Stripe SDK calls + plan validation.
The webhook (`checkout.session.completed`) is what actually flips
the store onto the new plan — these endpoints only initiate the
hosted-flow redirect.

Auth: requires JWT principal with role ∈ {`admin`, `owner`,
`superadmin`} — same gate as legacy `/admin/subscription/*`.
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Billing.Requests import (
    BillingPortalResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
)
from typing import Any


router = APIRouter()
_log = logging.getLogger(__name__)


_BILLING_ROLES = ("admin", "owner", "superadmin")


def _absolute_url(path: str) -> str:
    """Resolve an SPA-relative path to an absolute URL for Stripe.

    Stripe's `checkout.Session.create` (`success_url`, `cancel_url`)
    and `billing_portal.Session.create` (`return_url`) all REQUIRE
    fully-qualified HTTPS URLs.  Relative paths trigger an
    `InvalidRequestError` from the SDK ("URL must include scheme
    https://") which the Controller surfaces to the user as the
    generic "Payment service error" — exactly the bug pilot users
    reported on the Manage-on-Stripe button.

    `APP_BASE_URL` is the env var the rest of the codebase uses
    (daily-summary email links, locked-day digest, password reset,
    etc.); falls back to the canonical production host so dev
    builds without the env var still hit a real URL Stripe will
    accept.
    """
    base = (
        os.environ.get("APP_BASE_URL") or "https://dinerobook.com"
    ).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _require_billing_scope(claims: dict[str, Any]) -> int:
    if claims.get("role") not in _BILLING_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only store admins can manage billing.",
        )
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    return int(sid)


def _current_store(db: Session, store_id: int) -> Any:
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.post("/checkout", response_model=CheckoutSessionResponse)
def checkout_route(
    body: CheckoutSessionRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> CheckoutSessionResponse:
    """Mint a Stripe Checkout Session for `plan` and return the
    hosted Checkout URL. The SPA does `window.location.assign(url)`.

    422 — unknown plan slug.
    502 — Stripe is mis-configured or returned an error.
    """
    from api.Modules.Billing.Services import (
        InvalidPlanError, StripeServiceError, create_checkout_session,
    )
    sid = _require_billing_scope(claims)
    store = _current_store(db, sid)
    try:
        url = create_checkout_session(
            store, plan=body.plan,
            success_url=_absolute_url("/app/subscribe/success"),
            cancel_url=_absolute_url("/app/settings"),
        )
    except InvalidPlanError:
        raise HTTPException(status_code=422, detail="Invalid plan selected.")
    except StripeServiceError as exc:
        _log_stripe_error("checkout", exc, store_id=sid)
        raise HTTPException(
            status_code=502,
            detail=_stripe_user_message(exc),
        )
    return CheckoutSessionResponse(url=url)


@router.post("/portal", response_model=BillingPortalResponse)
def portal_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> BillingPortalResponse:
    """Mint a Stripe Billing Portal Session and return its URL.

    409 — store has no Stripe customer record yet (user must
    subscribe first via /billing/checkout).
    502 — Stripe error.
    """
    from api.Modules.Billing.Services import (
        StripeServiceError, create_billing_portal_session,
    )
    sid = _require_billing_scope(claims)
    store = _current_store(db, sid)
    if not store.stripe_customer_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "No billing account on file. "
                "Subscribe to a plan first."
            ),
        )
    try:
        url = create_billing_portal_session(
            store, return_url=_absolute_url("/app/settings"),
        )
    except StripeServiceError as exc:
        _log_stripe_error("portal", exc, store_id=sid)
        raise HTTPException(
            status_code=502,
            detail=_stripe_user_message(exc),
        )
    return BillingPortalResponse(url=url)


def _log_stripe_error(flow: str, exc: Exception, *, store_id: int) -> None:
    """Surface the underlying Stripe failure on every billing 502.

    The Service wraps `stripe.error.StripeError` as `StripeServiceError`
    with `__cause__` set to the original exception — so the user-
    facing 502 was generic but Sentry / structured logs had no
    record of WHICH Stripe error fired.  This helper writes a
    WARN-level log line with the underlying message + code so
    next time a pilot reports "Payment service error" we can read
    the actual cause in the logs without re-instrumenting.
    """
    cause = exc.__cause__
    # `stripe.error.StripeError` exposes `code`, `user_message`,
    # and `http_status` — read defensively in case the wrapping
    # ever changes.
    code = getattr(cause, "code", None) or getattr(cause, "error", None) or ""
    msg = (
        getattr(cause, "user_message", None)
        or str(cause)
        or "no detail from Stripe SDK"
    )
    _log.warning(
        "billing.%s_failed store_id=%s stripe_code=%r message=%r",
        flow, store_id, code, msg,
    )


# Stripe error codes that map to a clearer user-facing message.
# Anything not in this dict falls through to the generic
# "try again" string — those land in logs via _log_stripe_error
# so we can promote them to specific messages as patterns emerge.
_STRIPE_FRIENDLY: dict[str, str] = {
    # Customer Portal hasn't been configured in the Stripe Dashboard
    # for the current API mode (live / test).  Surfaces verbatim
    # from Stripe as either of these two codes depending on SDK
    # version, but the operator action is identical: configure +
    # save the Customer Portal at
    # https://dashboard.stripe.com/settings/billing/portal.
    "billing_portal_configuration_invalid": (
        "Stripe's billing portal isn't configured yet. "
        "An admin needs to enable + save the Customer Portal "
        "in the Stripe Dashboard before this button works."
    ),
}


def _stripe_user_message(exc: Exception) -> str:
    """Translate a known Stripe error code into a user-facing
    message; fall back to the generic "try again" string.

    Reads `exc.__cause__.code` (the Stripe SDK's machine-readable
    error code) and looks it up in the friendly-message table.
    Unrecognised codes still surface as "Payment service error.
    Please try again." but `_log_stripe_error` has already written
    the real code + message to the log line so an operator can
    map it + extend `_STRIPE_FRIENDLY`."""
    cause = exc.__cause__
    code = getattr(cause, "code", None) or ""
    if code and code in _STRIPE_FRIENDLY:
        return _STRIPE_FRIENDLY[code]
    # The portal-config error message also appears as a string match
    # in older Stripe SDK versions where `code` isn't populated.
    # Match the substring as a safety net.
    cause_text = str(cause or "")
    if "customer portal" in cause_text.lower() and "configur" in cause_text.lower():
        return _STRIPE_FRIENDLY["billing_portal_configuration_invalid"]
    return "Payment service error. Please try again."
