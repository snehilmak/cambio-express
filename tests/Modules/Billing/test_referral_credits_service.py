"""Unit tests for Billing.Services.apply_pending_referral_credits (PR 51).

The credit-application path has Stripe SDK side-effects, so the
tests stub the `stripe` module via `monkeypatch` rather than hit
the live SDK.
"""
from unittest.mock import MagicMock

import pytest


def _referee_store(
    *,
    referred_by_code_id=42,
    referee_credit_applied_at=None,
    stripe_customer_id="cus_referee",
    name="Referee Store",
    store_id=1,
):
    s = MagicMock()
    s.id = store_id
    s.referred_by_code_id = referred_by_code_id
    s.referee_credit_applied_at = referee_credit_applied_at
    s.stripe_customer_id = stripe_customer_id
    s.name = name
    return s


def _owner_store(*, stripe_customer_id="cus_owner", store_id=99):
    s = MagicMock()
    s.id = store_id
    s.stripe_customer_id = stripe_customer_id
    return s


def _referral_code(
    *,
    code="ABC12345",
    is_active=True,
    owner_store_id=99,
    reward_self_cents=10000,
    reward_referee_cents=5000,
    redeemed_count=0,
    rc_id=42,
):
    rc = MagicMock()
    rc.id = rc_id
    rc.code = code
    rc.is_active = is_active
    rc.owner_store_id = owner_store_id
    rc.reward_self_cents = reward_self_cents
    rc.reward_referee_cents = reward_referee_cents
    rc.redeemed_count = redeemed_count
    return rc


def _stripe_configured(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")


def _stub_stripe_balance_txn(monkeypatch, *, txn_id="txn_123"):
    """Replace stripe.Customer.create_balance_transaction with a stub
    that returns a MagicMock with the given .id attribute and records
    every call. Returns the mock for assertion."""
    import stripe
    fn = MagicMock()
    fn.return_value = MagicMock(id=txn_id)
    monkeypatch.setattr(stripe.Customer, "create_balance_transaction", fn)
    return fn


# ── early-return guards ────────────────────────────────────


def test_no_op_for_none_store():
    from api.Modules.Billing.Services import apply_pending_referral_credits
    db = MagicMock()
    apply_pending_referral_credits(db, None)
    assert db.add.call_count == 0


def test_no_op_for_organic_signup():
    """Store with no referred_by_code_id is organic — bail."""
    from api.Modules.Billing.Services import apply_pending_referral_credits
    db = MagicMock()
    s = _referee_store(referred_by_code_id=None)
    apply_pending_referral_credits(db, s)
    assert db.add.call_count == 0


def test_no_op_when_already_credited():
    """Idempotent: webhook retries should not re-credit."""
    from datetime import datetime
    from api.Modules.Billing.Services import apply_pending_referral_credits
    db = MagicMock()
    s = _referee_store(referee_credit_applied_at=datetime.utcnow())
    apply_pending_referral_credits(db, s)
    assert db.add.call_count == 0


def test_no_op_when_referral_code_missing():
    from api.Modules.Billing.Services import apply_pending_referral_credits
    db = MagicMock()
    db.get.return_value = None
    s = _referee_store()
    apply_pending_referral_credits(db, s)
    assert db.add.call_count == 0


def test_no_op_when_referral_code_inactive():
    """Deactivated referral code refuses new credits."""
    from api.Modules.Billing.Services import apply_pending_referral_credits
    db = MagicMock()
    db.get.return_value = _referral_code(is_active=False)
    s = _referee_store()
    apply_pending_referral_credits(db, s)
    assert db.add.call_count == 0


def test_no_op_when_owner_store_missing():
    """Owner store deleted — skip the credit but don't crash."""
    from api.Modules.Billing.Services import apply_pending_referral_credits
    db = MagicMock()
    rc = _referral_code()
    # First db.get → ReferralCode, second → owner Store (None)
    db.get.side_effect = [rc, None]
    s = _referee_store()
    apply_pending_referral_credits(db, s)
    assert db.add.call_count == 0


# ── happy path ─────────────────────────────────────────────


def test_credits_both_sides_and_records_redemption(monkeypatch):
    """Happy path: both Stripe credits succeed, redemption row written,
    counter bumped, lockout flag set."""
    from datetime import datetime
    from api.Modules.Billing.Services import apply_pending_referral_credits
    _stripe_configured(monkeypatch)
    fn = _stub_stripe_balance_txn(monkeypatch, txn_id="txn_OK")

    db = MagicMock()
    rc = _referral_code(redeemed_count=3)
    owner = _owner_store()
    db.get.side_effect = [rc, owner]
    s = _referee_store()

    apply_pending_referral_credits(db, s)

    # Two Stripe calls: referee + referrer.
    assert fn.call_count == 2

    # Redemption row added with both txn ids populated.
    assert db.add.call_count == 1
    redemption = db.add.call_args[0][0]
    assert redemption.referral_code_id == rc.id
    assert redemption.referee_store_id == s.id
    assert redemption.stripe_referee_txn_id == "txn_OK"
    assert redemption.stripe_self_txn_id == "txn_OK"
    assert isinstance(redemption.referee_credit_applied_at, datetime)
    assert isinstance(redemption.self_credit_applied_at, datetime)

    # Counter bumped + store lockout flag set.
    assert rc.redeemed_count == 4
    assert isinstance(s.referee_credit_applied_at, datetime)


def test_records_redemption_even_when_stripe_fails(monkeypatch):
    """Stripe error must NOT prevent the redemption row from being
    written — otherwise a webhook retry could double-post the same
    credit. txn_ids stay empty so the superadmin can reconcile."""
    import stripe
    from api.Modules.Billing.Services import apply_pending_referral_credits
    _stripe_configured(monkeypatch)

    fn = MagicMock(
        side_effect=stripe.error.StripeError("boom"),
    )
    monkeypatch.setattr(stripe.Customer, "create_balance_transaction", fn)

    db = MagicMock()
    rc = _referral_code()
    owner = _owner_store()
    db.get.side_effect = [rc, owner]
    s = _referee_store()

    apply_pending_referral_credits(db, s)

    # We still recorded the redemption.
    assert db.add.call_count == 1
    redemption = db.add.call_args[0][0]
    assert redemption.stripe_referee_txn_id == ""
    assert redemption.stripe_self_txn_id == ""
    # Lockout flag still set so retries don't re-attempt.
    assert s.referee_credit_applied_at is not None


def test_skips_stripe_when_no_secret_key(monkeypatch):
    """No STRIPE_SECRET_KEY configured (dev/test): skip the SDK
    calls but still write the redemption + lockout flag."""
    from api.Modules.Billing.Services import apply_pending_referral_credits
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    fn = _stub_stripe_balance_txn(monkeypatch)

    db = MagicMock()
    rc = _referral_code()
    owner = _owner_store()
    db.get.side_effect = [rc, owner]
    s = _referee_store()

    apply_pending_referral_credits(db, s)

    # No Stripe calls when not configured.
    assert fn.call_count == 0
    # But the redemption row + lockout still happen.
    assert db.add.call_count == 1


def test_skips_referee_credit_when_no_stripe_customer(monkeypatch):
    """Referee without stripe_customer_id (legacy / mid-flow): skip
    that side, still credit the referrer + record."""
    from api.Modules.Billing.Services import apply_pending_referral_credits
    _stripe_configured(monkeypatch)
    fn = _stub_stripe_balance_txn(monkeypatch)

    db = MagicMock()
    rc = _referral_code()
    owner = _owner_store()
    db.get.side_effect = [rc, owner]
    s = _referee_store(stripe_customer_id="")

    apply_pending_referral_credits(db, s)

    # Only the referrer side fired.
    assert fn.call_count == 1
    redemption = db.add.call_args[0][0]
    assert redemption.stripe_referee_txn_id == ""
    assert redemption.stripe_self_txn_id  # populated


def test_credit_amounts_are_negative_and_use_row_rates(monkeypatch):
    """The Service posts NEGATIVE amounts (credit on the customer
    balance) sized off the values pinned to the ReferralCode row,
    not the live constants."""
    from api.Modules.Billing.Services import apply_pending_referral_credits
    _stripe_configured(monkeypatch)
    fn = _stub_stripe_balance_txn(monkeypatch)

    db = MagicMock()
    # Use non-default amounts to prove the row's values are used.
    rc = _referral_code(reward_self_cents=20000, reward_referee_cents=7500)
    owner = _owner_store()
    db.get.side_effect = [rc, owner]
    s = _referee_store()

    apply_pending_referral_credits(db, s)

    # Pull the amount kwargs out of each call.
    calls = fn.call_args_list
    amounts = sorted(c.kwargs["amount"] for c in calls)
    assert amounts == [-20000, -7500]


# ── legacy Flask wrapper ───────────────────────────────────


