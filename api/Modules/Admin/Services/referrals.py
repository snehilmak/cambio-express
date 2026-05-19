"""Admin referrals Service.

Read-only — the legacy admin_referrals route also lazily mints a
ReferralCode if missing; the SPA endpoint mirrors that so trial-
to-paid stores get a code on their first visit. Caller commits.
"""
from urllib.parse import quote

from sqlalchemy.orm import Session
from typing import Any


class TrialPlanError(Exception):
    """Raised when an admin on a trial plan asks for their referral
    code. Mirrors the legacy redirect-with-flash behavior — the SPA
    surfaces it as a 409 with a clear message so the page can show
    "Upgrade to enable referrals"."""


def get_referral_payload(
    db: Session, *, store_id: int, host_origin: str,
) -> dict[str, Any]:
    """Return the self-service referral payload for the given store.
    Lazily mints a ReferralCode if missing (paid plans only — trial
    stores raise TrialPlanError).

    `host_origin` is e.g. "https://dinerobook.com" — the share_url
    embeds it directly so a cashier on the SPA doesn't have to
    derive the canonical hostname client-side.
    """
    from api.Modules.Billing.Models import ReferralCode, ReferralRedemption
    from api.Modules.Billing.Services import (
        ensure_referral_code, store_has_paid_plan,
    )
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, store_id)
    if store is None:
        raise ValueError("Store not found")
    if not store_has_paid_plan(store):
        raise TrialPlanError(
            "Referrals unlock when your subscription is active.",
        )
    rc = ensure_referral_code(db, store)
    db.flush()

    redemptions = (
        db.query(ReferralRedemption)
          .filter_by(referral_code_id=rc.id)
          .order_by(ReferralRedemption.redeemed_at.desc())
          .all()
    )
    credits_earned_cents = sum(
        rc.reward_self_cents for r in redemptions
        if r.self_credit_applied_at
    )

    share_url = (
        f"{host_origin.rstrip('/')}/signup?ref={quote(rc.code, safe='')}"
    )

    return {
        "code":                 rc.code,
        "is_active":            bool(rc.is_active),
        "reward_self_cents":    int(rc.reward_self_cents or 0),
        "reward_referee_cents": int(rc.reward_referee_cents or 0),
        "redeemed_count":       int(rc.redeemed_count or 0),
        "credits_earned_cents": int(credits_earned_cents),
        "share_url":            share_url,
        "redemptions": [
            {
                "redeemed_at":            r.redeemed_at.isoformat()
                                          if r.redeemed_at else "",
                "referee_store_id":       int(r.referee_store_id),
                "self_credit_applied":    bool(r.self_credit_applied_at),
                "referee_credit_applied": bool(r.referee_credit_applied_at),
                "stripe_self_txn_id":     r.stripe_self_txn_id or "",
            }
            for r in redemptions
        ],
    }
