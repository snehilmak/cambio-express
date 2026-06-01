"""Discount-code SQL helpers for the superadmin promo manager.

Promo codes are minted manually via the legacy site (Stripe coupon
creation needs careful error handling). The superadmin SPA only
lists + toggles them, so this Repository covers read + by-id
lookup only — no create/delete.
"""
from sqlalchemy.orm import Session

from api.Modules.Billing.Models import DiscountCode


def list_discount_codes(db: Session) -> list[DiscountCode]:
    """Every promo code, newest first."""
    return (
        db.query(DiscountCode)
          .order_by(DiscountCode.created_at.desc())
          .all()
    )


def get_discount_code(
    db: Session, discount_id: int,
) -> DiscountCode | None:
    """Single discount by id, or None."""
    return (
        db.query(DiscountCode)
          .filter(DiscountCode.id == discount_id)
          .one_or_none()
    )
