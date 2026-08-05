"""Referral codes — full Service.

Owns every read/write path that touches `ReferralCode` and
`ReferralRedemption`:

  - `new_referral_code(db)`            — mint a unique 8-char code.
  - `ensure_referral_code(db, store)`  — idempotent get-or-mint.
  - `lookup_referral_code(db, raw)`    — strip + uppercase + active-only.
  - `apply_pending_referral_credits(db, referee_store)` —
    on the referee's *paid* conversion, post both Stripe customer-
    balance credits + record a ReferralRedemption row so webhook
    retries can't double-credit.

Per CLAUDE.md invariant #12:
- One ReferralCode row per store (`owner_store_id` is unique).
- `ensure_referral_code` is idempotent.
- Code lookup is uppercase + active-only (deactivated codes
  refuse new redemptions).
- Credits only apply on the referee's *paid* conversion, not at
  trial — keeps us from paying for signups that churn.
- `Store.referee_credit_applied_at` is the lockout flag; once set,
  the credit path is a no-op.
"""
import logging
import secrets
import string

import stripe
from sqlalchemy.orm import Session

from api.Modules.Billing.Models import (
    ReferralCode,
    ReferralRedemption,
    Store,
)
from api.Modules.Billing.Services.config import stripe_is_configured
from api.Core.Clock import utc_now


logger = logging.getLogger(__name__)


# Stripe customer-balance credits applied on each referee
# conversion. Stored on the row at mint time so historical
# redemptions keep the rate they were promised at.
REFERRAL_SELF_CENTS = 10000      # $100 for the referrer
REFERRAL_REFEREE_CENTS = 5000    # $50 for the new (referee) store

# Uppercase alphanumeric — no lowercase, no symbols, no ambiguous
# I/O/0/1. Operators read these out loud over the phone, so
# legibility matters more than entropy.
_REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
_REFERRAL_CODE_LENGTH = 8
_REFERRAL_CODE_MINT_RETRIES = 12


def new_referral_code(db: Session) -> str:
    """Mint an 8-char uppercase alphanumeric referral code.

    Tries up to 12 times before giving up — that ceiling is
    effectively unreachable at any realistic volume (36^8 ≈ 2.8e12
    codes).
    """
    for _ in range(_REFERRAL_CODE_MINT_RETRIES):
        code = "".join(
            secrets.choice(_REFERRAL_CODE_ALPHABET)
            for _ in range(_REFERRAL_CODE_LENGTH)
        )
        existing = db.query(ReferralCode).filter_by(code=code).first()
        if existing is None:
            return code
    raise RuntimeError("Could not mint a unique referral code")


def ensure_referral_code(db: Session, store: Store | None) -> ReferralCode | None:
    """Return the store's ReferralCode, creating it on demand.

    Admins only see the crown once they're on a paid plan, so call
    sites should already have checked `store.plan in {basic, pro}`
    — we don't enforce here (the superadmin / testing flows may
    want to pre-mint).

    Caller commits: we `flush()` so the new row gets an ID, but
    leave the surrounding transaction to whatever flow triggered
    the lazy mint (context processor, webhook, etc.).
    """
    if not store:
        return None
    rc = (
        db.query(ReferralCode)
          .filter_by(owner_store_id=store.id)
          .first()
    )
    if rc is not None:
        return rc
    rc = ReferralCode(
        code=new_referral_code(db),
        owner_store_id=store.id,
        reward_self_cents=REFERRAL_SELF_CENTS,
        reward_referee_cents=REFERRAL_REFEREE_CENTS,
    )
    db.add(rc)
    db.flush()
    return rc


def lookup_referral_code(db: Session, raw: str | None) -> ReferralCode | None:
    """Return the active ReferralCode matching the raw input, or None.

    Accepts either the bare code string or a URL like
    `/signup?ref=ABC123` — we strip and uppercase, the URL
    extraction happens at the form-parse boundary.

    Inactive codes (`is_active=False`) refuse new redemptions even
    if a referee submits one — keeps the superadmin's "deactivate
    this referral" toggle from being defeated by stale signup links.
    """
    if not raw:
        return None
    code = raw.strip().upper()
    if not code:
        return None
    return (
        db.query(ReferralCode)
          .filter_by(code=code, is_active=True)
          .first()
    )


def apply_pending_referral_credits(
    db: Session, referee_store: Store | None,
) -> None:
    """Apply Stripe customer-balance credits to both sides of a
    referral, then record a ReferralRedemption so webhook retries
    can't double-credit.

    Called from the `checkout.session.completed` webhook when the
    referee's store transitions from trial → paid. No-op when:
      - no store / no `referred_by_code_id` (organic signup)
      - already credited (`referee_credit_applied_at` set)
      - the referral code is missing or inactive
      - the owner store has been deleted

    Stripe side-effects:
      - referee gets `reward_referee_cents` credited to their
        Stripe customer (negative balance transaction).
      - referrer gets `reward_self_cents` credited to theirs.

    On Stripe failure we still record the ReferralRedemption row
    (with empty txn IDs) so a webhook retry can't post the same
    credit twice. The superadmin reconciles failed credits manually.

    Caller commits — keeps this transactional alongside the plan
    transition that triggered it.
    """
    if not referee_store or not referee_store.referred_by_code_id:
        return
    if referee_store.referee_credit_applied_at:
        return

    rc = db.get(ReferralCode, referee_store.referred_by_code_id)
    if not rc or not rc.is_active:
        return
    owner = db.get(Store, rc.owner_store_id)
    if not owner:
        return

    now = utc_now()
    referee_txn_id = ""
    if referee_store.stripe_customer_id and stripe_is_configured():
        try:
            txn = stripe.Customer.create_balance_transaction(
                referee_store.stripe_customer_id,
                amount=-abs(rc.reward_referee_cents),
                currency="usd",
                description=(
                    f"Referral credit — welcome! Used code {rc.code}"
                ),
                metadata={"referral_code": rc.code, "side": "referee"},
            )
            referee_txn_id = getattr(txn, "id", "") or ""
        except stripe.error.StripeError as e:
            logger.warning(
                "referee credit failed for store %s: %s",
                referee_store.id, e,
            )

    self_txn_id = ""
    if owner.stripe_customer_id and stripe_is_configured():
        try:
            txn = stripe.Customer.create_balance_transaction(
                owner.stripe_customer_id,
                amount=-abs(rc.reward_self_cents),
                currency="usd",
                description=(
                    f"Referral reward — {referee_store.name} "
                    "just subscribed"
                ),
                metadata={
                    "referral_code": rc.code,
                    "side": "referrer",
                    "referee_store_id": str(referee_store.id),
                },
            )
            self_txn_id = getattr(txn, "id", "") or ""
        except stripe.error.StripeError as e:
            logger.warning(
                "referrer credit failed for referrer %s: %s",
                owner.id, e,
            )

    db.add(ReferralRedemption(
        referral_code_id=rc.id,
        referee_store_id=referee_store.id,
        self_credit_applied_at=now if self_txn_id else None,
        referee_credit_applied_at=now if referee_txn_id else None,
        stripe_self_txn_id=self_txn_id,
        stripe_referee_txn_id=referee_txn_id,
    ))
    rc.redeemed_count = (rc.redeemed_count or 0) + 1
    referee_store.referee_credit_applied_at = now
