"""Unit tests for Billing.Services.referrals (PR 50)."""
from unittest.mock import MagicMock, patch


def _store(store_id=1):
    s = MagicMock()
    s.id = store_id
    return s


# ── new_referral_code ──────────────────────────────────────


def test_new_referral_code_format():
    """8-char uppercase alphanumeric; never lowercase, never symbols."""
    from api.Modules.Billing.Services import new_referral_code
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
    code = new_referral_code(db)
    assert len(code) == 8
    assert code.isupper() or code.isdigit() or all(
        c.isupper() or c.isdigit() for c in code
    )
    assert code.isalnum()


def test_new_referral_code_skips_collisions():
    """If the first roll collides with an existing code, the helper
    rolls again. Test by feeding back 'taken' once and None thereafter."""
    from api.Modules.Billing.Services import new_referral_code
    db = MagicMock()
    chain = MagicMock()
    db.query.return_value = chain
    chain.filter_by.return_value = chain
    # First lookup hits a collision; second returns None.
    chain.first.side_effect = [MagicMock(), None]
    code = new_referral_code(db)
    assert len(code) == 8
    # We rolled twice, so .first() got called twice.
    assert chain.first.call_count == 2


def test_new_referral_code_gives_up_after_retries():
    """If every roll collides for 12 attempts, raise RuntimeError so
    the caller doesn't silently mint a duplicate."""
    from api.Modules.Billing.Services import new_referral_code
    db = MagicMock()
    chain = MagicMock()
    db.query.return_value = chain
    chain.filter_by.return_value = chain
    # Always return a collision.
    chain.first.return_value = MagicMock()
    import pytest
    with pytest.raises(RuntimeError, match="unique referral code"):
        new_referral_code(db)


# ── ensure_referral_code ───────────────────────────────────


def test_ensure_referral_code_returns_none_for_no_store():
    from api.Modules.Billing.Services import ensure_referral_code
    db = MagicMock()
    assert ensure_referral_code(db, None) is None


def test_ensure_referral_code_returns_existing():
    """Idempotent: if a row already exists for this store, return it
    instead of minting a duplicate."""
    from api.Modules.Billing.Services import ensure_referral_code
    existing = MagicMock()
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = existing
    rc = ensure_referral_code(db, _store(42))
    assert rc is existing
    # No mint, no add.
    assert db.add.call_count == 0


def test_ensure_referral_code_creates_when_missing():
    """First call for this store mints a fresh code, adds + flushes."""
    from api.Modules.Billing.Services import ensure_referral_code
    db = MagicMock()
    chain = MagicMock()
    db.query.return_value = chain
    chain.filter_by.return_value = chain
    # Two .first() calls in the flow:
    #   1) ensure_referral_code's owner_store_id lookup → no existing
    #   2) new_referral_code's collision check → no collision
    chain.first.side_effect = [None, None]
    rc = ensure_referral_code(db, _store(42))
    assert rc is not None
    assert db.add.call_count == 1
    assert db.flush.call_count == 1


def test_ensure_referral_code_uses_stored_reward_amounts():
    """The minted row pins the current $100 / $50 rates so historical
    redemptions keep what they were promised at."""
    from api.Modules.Billing.Services import (
        REFERRAL_REFEREE_CENTS,
        REFERRAL_SELF_CENTS,
        ensure_referral_code,
    )
    db = MagicMock()
    chain = MagicMock()
    db.query.return_value = chain
    chain.filter_by.return_value = chain
    chain.first.side_effect = [None, None]
    rc = ensure_referral_code(db, _store(42))
    assert rc.reward_self_cents == REFERRAL_SELF_CENTS
    assert rc.reward_referee_cents == REFERRAL_REFEREE_CENTS


# ── lookup_referral_code ───────────────────────────────────


def test_lookup_referral_code_none_for_blank():
    from api.Modules.Billing.Services import lookup_referral_code
    db = MagicMock()
    assert lookup_referral_code(db, None) is None
    assert lookup_referral_code(db, "") is None
    assert lookup_referral_code(db, "   ") is None


def test_lookup_referral_code_uppercases():
    """User submits lowercase code from a URL → match still works."""
    from api.Modules.Billing.Services import lookup_referral_code
    found = MagicMock()
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = found
    assert lookup_referral_code(db, "abc12345") is found
    db.query.return_value.filter_by.assert_called_with(
        code="ABC12345", is_active=True,
    )


def test_lookup_referral_code_strips_whitespace():
    from api.Modules.Billing.Services import lookup_referral_code
    found = MagicMock()
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = found
    assert lookup_referral_code(db, "  ABC12345  ") is found
    db.query.return_value.filter_by.assert_called_with(
        code="ABC12345", is_active=True,
    )


def test_lookup_referral_code_filters_active_only():
    """Inactive codes (`is_active=False`) refuse new redemptions."""
    from api.Modules.Billing.Services import lookup_referral_code
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
    assert lookup_referral_code(db, "ABC12345") is None
    db.query.return_value.filter_by.assert_called_with(
        code="ABC12345", is_active=True,
    )


def test_legacy_app_constants_unchanged():
    """The $100 / $50 rates are part of the public PR contract.
    If you change these, every store with an existing ReferralCode
    keeps its old rate (the row stores them); but new mints will
    use the new constant. Reviewers should see this as an explicit
    change."""
    from app import REFERRAL_REFEREE_CENTS, REFERRAL_SELF_CENTS
    assert REFERRAL_SELF_CENTS == 10000
    assert REFERRAL_REFEREE_CENTS == 5000
