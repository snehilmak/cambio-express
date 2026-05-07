"""Unit tests for BankSync.Services.matcher (PR 70)."""
from unittest.mock import MagicMock


def _rule(*, enabled=True, desc_match_type=None, desc_match_value=None,
          sign_filter=None, amount_min_cents=None, amount_max_cents=None,
          account_filter_id=None):
    """Minimal stand-in for a BankRule row.

    `enabled=None` is the transient-row case (un-persisted, before
    SQLAlchemy default fires). `enabled=False` is the disabled
    case."""
    r = MagicMock()
    r.enabled = enabled
    r.desc_match_type = desc_match_type
    r.desc_match_value = desc_match_value
    r.sign_filter = sign_filter
    r.amount_min_cents = amount_min_cents
    r.amount_max_cents = amount_max_cents
    r.account_filter_id = account_filter_id
    return r


def _txn(*, description="", amount_cents=0, stripe_bank_account_id=None):
    t = MagicMock()
    t.description = description
    t.amount_cents = amount_cents
    t.stripe_bank_account_id = stripe_bank_account_id
    return t


# ── enabled flag ───────────────────────────────────────────


def test_disabled_rule_never_matches():
    from api.Modules.BankSync.Services import rule_matches
    rule = _rule(enabled=False)
    assert rule_matches(rule, _txn()) is False


def test_transient_rule_with_none_enabled_can_match():
    """Un-persisted rule (enabled=None) treated as True so the
    operator can preview a match before saving."""
    from api.Modules.BankSync.Services import rule_matches
    rule = _rule(enabled=None)
    assert rule_matches(rule, _txn()) is True


def test_enabled_rule_with_no_conditions_matches_everything():
    from api.Modules.BankSync.Services import rule_matches
    assert rule_matches(_rule(), _txn()) is True


# ── description match ──────────────────────────────────────


def test_desc_contains_match_is_case_insensitive():
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(desc_match_type="contains",
              desc_match_value="REMOTE")
    assert rule_matches(r, _txn(description="remote deposit fee")) is True
    assert rule_matches(r, _txn(description="WIRE FEE")) is False


def test_desc_starts_with_match():
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(desc_match_type="starts_with",
              desc_match_value="REMOTE")
    assert rule_matches(r, _txn(description="REMOTE deposit")) is True
    assert rule_matches(r, _txn(description="x REMOTE")) is False


def test_desc_equals_match():
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(desc_match_type="equals",
              desc_match_value="WIRE FEE")
    assert rule_matches(r, _txn(description="wire fee")) is True
    assert rule_matches(r, _txn(description="WIRE FEE 04/29")) is False


def test_desc_regex_match_case_insensitive():
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(desc_match_type="regex",
              desc_match_value=r"^REMOTE.*FEE$")
    assert rule_matches(r, _txn(description="remote deposit fee")) is True
    assert rule_matches(r, _txn(description="WIRE FEE")) is False


def test_desc_regex_invalid_pattern_returns_false():
    """Bad regex must NOT crash the sync — refuse to match."""
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(desc_match_type="regex",
              desc_match_value="[unclosed")
    assert rule_matches(r, _txn(description="anything")) is False


def test_desc_match_skipped_when_either_field_missing():
    """`desc_match_type` set but `desc_match_value` empty → don't
    apply the description filter at all."""
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(desc_match_type="contains", desc_match_value="")
    # Other conditions all unset → match.
    assert rule_matches(r, _txn(description="anything")) is True


# ── sign filter ────────────────────────────────────────────


def test_credit_filter_excludes_debits():
    """credit filter requires amount_cents >= 0."""
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(sign_filter="credit")
    assert rule_matches(r, _txn(amount_cents=100)) is True
    assert rule_matches(r, _txn(amount_cents=-100)) is False


def test_debit_filter_excludes_credits():
    """debit filter requires amount_cents < 0."""
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(sign_filter="debit")
    assert rule_matches(r, _txn(amount_cents=-100)) is True
    assert rule_matches(r, _txn(amount_cents=100)) is False
    # Zero counts as credit-side (>= 0) so debit excludes it.
    assert rule_matches(r, _txn(amount_cents=0)) is False


# ── amount range ───────────────────────────────────────────


def test_amount_min_uses_absolute_cents():
    """A -300 cent debit should pass min=200 because |300| >= 200."""
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(amount_min_cents=200)
    assert rule_matches(r, _txn(amount_cents=-300)) is True
    assert rule_matches(r, _txn(amount_cents=-100)) is False


def test_amount_max_uses_absolute_cents():
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(amount_max_cents=500)
    assert rule_matches(r, _txn(amount_cents=-300)) is True
    assert rule_matches(r, _txn(amount_cents=-1000)) is False


def test_amount_range_bounded_both_sides():
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(amount_min_cents=100, amount_max_cents=500)
    assert rule_matches(r, _txn(amount_cents=-300)) is True
    assert rule_matches(r, _txn(amount_cents=-50)) is False
    assert rule_matches(r, _txn(amount_cents=-9999)) is False


# ── account filter ─────────────────────────────────────────


def test_account_filter_pins_to_one_account():
    from api.Modules.BankSync.Services import rule_matches
    r = _rule(account_filter_id=42)
    assert rule_matches(r, _txn(stripe_bank_account_id=42)) is True
    assert rule_matches(r, _txn(stripe_bank_account_id=99)) is False


def test_account_filter_unset_matches_any_account():
    """`account_filter_id=None` → no account constraint."""
    from api.Modules.BankSync.Services import rule_matches
    r = _rule()
    assert rule_matches(r, _txn(stripe_bank_account_id=42)) is True
    assert rule_matches(r, _txn(stripe_bank_account_id=99)) is True


# ── find_matching_rule (DB integration) ────────────────────


def test_find_matching_rule_returns_none_when_no_rules():
    from app import app as flask_app, db, BankRule
    from api.Modules.BankSync.Services import find_matching_rule
    with flask_app.app_context():
        BankRule.query.delete()
        db.session.commit()
        assert find_matching_rule(db.session, 1, _txn()) is None


def test_find_matching_rule_picks_lowest_priority_first():
    """priority=0 wins over priority=1 — even when both match."""
    from app import app as flask_app, db, BankRule
    from api.Modules.BankSync.Services import find_matching_rule
    with flask_app.app_context():
        BankRule.query.delete()
        db.session.commit()
        store_id = 99
        # Both match every transaction (no conditions set).
        low = BankRule(
            store_id=store_id, priority=0, enabled=True,
            target_kind="cash_expense",
            description="Low priority rule",
        )
        high = BankRule(
            store_id=store_id, priority=1, enabled=True,
            target_kind="cash_expense",
            description="High priority rule",
        )
        db.session.add_all([high, low])
        db.session.commit()
        result = find_matching_rule(
            db.session, store_id, _txn(amount_cents=100),
        )
        assert result.priority == 0


def test_find_matching_rule_skips_disabled_rules():
    """Disabled rules never match, regardless of priority."""
    from app import app as flask_app, db, BankRule
    from api.Modules.BankSync.Services import find_matching_rule
    with flask_app.app_context():
        BankRule.query.delete()
        db.session.commit()
        store_id = 100
        # The lowest-priority rule is disabled — should be skipped.
        db.session.add(BankRule(
            store_id=store_id, priority=0, enabled=False,
            target_kind="cash_expense",
            description="disabled",
        ))
        db.session.add(BankRule(
            store_id=store_id, priority=1, enabled=True,
            target_kind="cash_expense",
            description="enabled",
        ))
        db.session.commit()
        result = find_matching_rule(
            db.session, store_id, _txn(amount_cents=100),
        )
        assert result.priority == 1


def test_find_matching_rule_filters_by_store():
    """Rules in a different store don't apply."""
    from app import app as flask_app, db, BankRule
    from api.Modules.BankSync.Services import find_matching_rule
    with flask_app.app_context():
        BankRule.query.delete()
        db.session.commit()
        # Rule belongs to store 1; we query store 2.
        db.session.add(BankRule(
            store_id=1, priority=0, enabled=True,
            target_kind="cash_expense",
            description="for-store-1",
        ))
        db.session.commit()
        result = find_matching_rule(
            db.session, 2, _txn(amount_cents=100),
        )
        assert result is None


# ── legacy Flask wrappers ──────────────────────────────────


def test_legacy_bank_rule_matches_delegates():
    from app import _bank_rule_matches as legacy
    r = _rule(desc_match_type="contains",
              desc_match_value="REMOTE")
    assert legacy(r, _txn(description="remote fee")) is True
    assert legacy(r, _txn(description="wire")) is False


def test_legacy_find_matching_rule_delegates():
    from app import app as flask_app, db, BankRule
    from app import _find_matching_rule as legacy
    with flask_app.app_context():
        BankRule.query.delete()
        db.session.commit()
        # Empty rule table → None
        assert legacy(1, _txn()) is None
