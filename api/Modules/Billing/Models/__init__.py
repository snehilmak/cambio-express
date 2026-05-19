"""Billing — Models.

Five classes:

* ``ReferralCode``           — one per-store referral code minted at
                                first paid conversion.
* ``ReferralRedemption``     — one per new store that signed up with
                                a referral code; tracks Stripe
                                credit-application status.
* ``DiscountCode``           — superadmin-minted promo, optionally
                                synced to Stripe.
* ``FeatureFlag``            — global feature switch (default on/off).
* ``StoreFeatureOverride``   — per-store override of a FeatureFlag's
                                global default.

``Store`` is re-exported from ``api/Modules/Tenancy/Models`` for the
existing ``from api.Modules.Billing.Models import Store`` call sites.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)

from api.Core.Database import Base


class ReferralCode(Base):
    """One code per store, minted the first time the store goes onto
    a paid plan. The owner shares this code; every time a new store
    signs up with it and then converts to paid:

      - the owner gets ``reward_self_cents`` credited to their Stripe
        customer balance
      - the referee gets ``reward_referee_cents`` credited to theirs

    Credits only apply on the referee's *paid* conversion, not at
    trial — keeps us from paying for signups that churn.
    """

    __tablename__ = "referral_code"
    id                    = Column(Integer, primary_key=True)
    code                  = Column(String(12), unique=True, nullable=False)
    owner_store_id        = Column(Integer, ForeignKey("store.id"),
                                    unique=True, nullable=False)
    reward_self_cents     = Column(Integer, default=10000)  # $100
    reward_referee_cents  = Column(Integer, default=5000)   # $50
    is_active             = Column(Boolean, default=True)
    redeemed_count        = Column(Integer, default=0)
    created_at            = Column(DateTime, default=datetime.utcnow)


class ReferralRedemption(Base):
    """One row per new store that signed up with a referral code.
    Flags track whether the Stripe customer-balance credit on each
    side has been applied — so a webhook retry can't double-credit.
    """

    __tablename__ = "referral_redemption"
    id                      = Column(Integer, primary_key=True)
    referral_code_id        = Column(Integer, ForeignKey("referral_code.id"), nullable=False)
    referee_store_id        = Column(Integer, ForeignKey("store.id"),
                                      unique=True, nullable=False)
    redeemed_at             = Column(DateTime, default=datetime.utcnow)
    self_credit_applied_at  = Column(DateTime, nullable=True)
    referee_credit_applied_at = Column(DateTime, nullable=True)
    stripe_self_txn_id      = Column(String(60), default="")
    stripe_referee_txn_id   = Column(String(60), default="")


class DiscountCode(Base):
    """Promo code the superadmin mints; synced to Stripe when possible.

    Either ``percent_off`` *or* ``amount_off_cents`` is set — never
    both. When Stripe is reachable we create a coupon + promotion
    code and store their IDs; customers can then enter the code at
    checkout because ``subscribe_checkout`` passes
    ``allow_promotion_codes=True``.
    """

    __tablename__ = "discount_code"
    id                        = Column(Integer, primary_key=True)
    code                      = Column(String(40), unique=True, nullable=False)
    label                     = Column(String(120), default="")
    percent_off               = Column(Integer, nullable=True)   # 1..100
    amount_off_cents          = Column(Integer, nullable=True)   # USD cents
    duration                  = Column(String(16), default="once")  # once | forever | repeating
    duration_in_months        = Column(Integer, nullable=True)
    max_redemptions           = Column(Integer, nullable=True)
    redeemed_count            = Column(Integer, default=0)
    expires_at                = Column(DateTime, nullable=True)
    stripe_coupon_id          = Column(String(60), default="")
    stripe_promotion_code_id  = Column(String(60), default="")
    is_active                 = Column(Boolean, default=True)
    created_at                = Column(DateTime, default=datetime.utcnow)
    created_by                = Column(Integer, ForeignKey("user.id"), nullable=True)

    @property
    def value_label(self) -> str:
        if self.percent_off:
            return f"{self.percent_off}% off"
        if self.amount_off_cents:
            return f"${self.amount_off_cents / 100:.2f} off"
        return "—"


class FeatureFlag(Base):
    """Global feature switch the superadmin can flip without a deploy.

    ``enabled_by_default`` is the baseline; ``StoreFeatureOverride``
    can flip it for a single store (e.g. beta-test a feature with
    one customer).
    """

    __tablename__ = "feature_flag"
    id                 = Column(Integer, primary_key=True)
    key                = Column(String(60), unique=True, nullable=False)
    label              = Column(String(120), default="")
    description        = Column(Text, default="")
    enabled_by_default = Column(Boolean, default=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


class StoreFeatureOverride(Base):
    """Per-store override of a FeatureFlag's global default."""

    __tablename__ = "store_feature_override"
    id         = Column(Integer, primary_key=True)
    store_id   = Column(Integer, ForeignKey("store.id"), nullable=False)
    flag_key   = Column(String(60), nullable=False)
    enabled    = Column(Boolean, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    __table_args__ = (UniqueConstraint("store_id", "flag_key"),)


# Re-export Store for existing
# ``from api.Modules.Billing.Models import Store`` call sites.
from api.Modules.Tenancy.Models import Store  # noqa: E402


__all__ = [
    "DiscountCode", "FeatureFlag", "ReferralCode", "ReferralRedemption",
    "Store", "StoreFeatureOverride",
]
