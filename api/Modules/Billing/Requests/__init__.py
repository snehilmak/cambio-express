"""Billing — Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict, Field


class CheckoutSessionRequest(BaseModel):
    """POST body for /api/v2/billing/checkout. `plan` is one of the
    keys recognised by `create_checkout_session` —
    `basic` / `basic_yearly` / `pro` / `pro_yearly` (yearly options
    only available when their Stripe price IDs are configured)."""
    model_config = ConfigDict(extra="forbid")

    plan: str = Field(..., min_length=1, max_length=40)


class CheckoutSessionResponse(BaseModel):
    """Mint succeeded — `url` is the Stripe-hosted Checkout URL the
    SPA should redirect the user to."""
    model_config = ConfigDict(extra="forbid")

    url: str


class BillingPortalResponse(BaseModel):
    """Mint succeeded — `url` is the Stripe-hosted Billing Portal
    URL the SPA should redirect the user to."""
    model_config = ConfigDict(extra="forbid")

    url: str


__all__ = [
    "BillingPortalResponse",
    "CheckoutSessionRequest",
    "CheckoutSessionResponse",
]
