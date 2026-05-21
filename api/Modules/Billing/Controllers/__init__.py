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
    except StripeServiceError:
        raise HTTPException(
            status_code=502,
            detail="Payment service error. Please try again.",
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
    except StripeServiceError:
        raise HTTPException(
            status_code=502,
            detail="Payment service error. Please try again.",
        )
    return BillingPortalResponse(url=url)
