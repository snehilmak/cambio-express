"""Pydantic schemas for the platform discount-code endpoints.

Read-only list + activation toggle. Stripe coupon mint + new-code
generation stays on the legacy site for now (those need careful
Stripe error handling). This module is safe to operate without
Stripe being reachable — it never makes outbound API calls.
"""
from pydantic import BaseModel, ConfigDict


class DiscountCodeRow(BaseModel):
    """One DiscountCode row. `value_label` carries the legacy
    derived display text ("$5 off" / "20% off") so the SPA renders
    without recomputing. `is_redeemable` is True when the code is
    active AND not expired AND under any max_redemptions cap."""
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    label: str
    percent_off: int | None
    amount_off_cents: int | None
    value_label: str
    duration: str
    duration_in_months: int | None
    max_redemptions: int | None
    redeemed_count: int
    expires_at: str
    is_active: bool
    is_redeemable: bool
    stripe_coupon_id: str
    stripe_promotion_code_id: str
    created_at: str


class DiscountCodeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[DiscountCodeRow]
    total: int


class DiscountCodeToggleRequest(BaseModel):
    """POST body for /superadmin/discounts/{id}/toggle. Explicit
    `is_active` so callers don't accidentally flip the wrong way
    when their cached row is stale."""
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class DiscountCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discount: DiscountCodeRow
