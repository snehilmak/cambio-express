"""Referral codes — pure-DB helpers.

Three small helpers that own the read/write contract for
`ReferralCode` rows. The Stripe-touching credit-application path
(`apply_pending_referral_credits`) stays in `app.py` for now —
it has Stripe SDK side-effects + Flask logger usage that don't
belong in a Service yet.

Per CLAUDE.md invariant #12:
- One ReferralCode row per store (`owner_store_id` is unique).
- `ensure_referral_code` is idempotent: returns the existing row
  if present, mints a new one otherwise.
- Code lookup is uppercase + active-only (deactivated codes
  refuse new redemptions).
"""
import secrets
import string

from sqlalchemy.orm import Session

from api.Modules.Billing.Models import ReferralCode, Store


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
