"""Unit tests for BankSync.Services.builtin_rules (PR 58)."""
from unittest.mock import MagicMock


def _txn(description=""):
    t = MagicMock()
    t.description = description
    return t


def _account(last4=""):
    a = MagicMock()
    a.last4 = last4
    return a


# ── match_builtin_bank_rule ────────────────────────────────


def test_match_remote_deposit_fee_only_on_msb_account():
    """REMOTE DEPOSIT FEE is gated on last4='0230'. Other accounts
    must NOT fire — that's a money-routing invariant."""
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    # Right account → matches
    result = match_builtin_bank_rule(
        _txn("REMOTE DEPOSIT FEE 04/29"), _account("0230"),
    )
    assert result == "bank_charge_230"
    # Wrong account → no match
    result = match_builtin_bank_rule(
        _txn("REMOTE DEPOSIT FEE 04/29"), _account("0210"),
    )
    assert result is None


def test_match_below_avg_bal_fee_any_account():
    """Account-agnostic rule (want_last4='') fires on any account."""
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    assert match_builtin_bank_rule(
        _txn("BELOW AVG BAL FEE"), _account("0210"),
    ) == "bank_charge_210"
    assert match_builtin_bank_rule(
        _txn("BELOW AVG BAL FEE"), _account("0230"),
    ) == "bank_charge_230"


def test_match_substring_case_insensitive():
    """Description matching is uppercase-folded."""
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    result = match_builtin_bank_rule(
        _txn("below avg bal fee for april"), _account("9999"),
    )
    assert result == "bank_charge_9999"


def test_match_strips_leading_zeros_in_per_account_slug():
    """last4 '0210' produces 'bank_charge_210', not
    'bank_charge_0210' — historic convention."""
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    result = match_builtin_bank_rule(
        _txn("MSB MONTHLY FEE"), _account("0210"),
    )
    assert result == "bank_charge_210"


def test_match_keeps_all_zero_last4():
    """If last4 is all zeros, lstrip('0') returns '', so we keep
    the original last4 string (never produce 'bank_charge_')."""
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    result = match_builtin_bank_rule(
        _txn("MSB MONTHLY FEE"), _account("0000"),
    )
    assert result == "bank_charge_0000"


def test_match_no_account_returns_none_for_per_account():
    """Per-account sentinel needs a last4. Without it we'd rather
    not fire than tag with a phantom slug."""
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    assert match_builtin_bank_rule(
        _txn("BELOW AVG BAL FEE"), None,
    ) is None
    assert match_builtin_bank_rule(
        _txn("BELOW AVG BAL FEE"), _account(""),
    ) is None


def test_match_unknown_description_returns_none():
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    result = match_builtin_bank_rule(
        _txn("RANDOM TRANSACTION"), _account("0210"),
    )
    assert result is None


def test_match_handles_none_description():
    """Defensive: a row with description=None shouldn't crash."""
    from api.Modules.BankSync.Services import match_builtin_bank_rule
    t = MagicMock()
    t.description = None
    assert match_builtin_bank_rule(t, _account("0210")) is None


# ── is_bank_charge_slug ────────────────────────────────────


def test_is_bank_charge_slug_matches_generic():
    from api.Modules.BankSync.Services import is_bank_charge_slug
    assert is_bank_charge_slug("bank_charge") is True


def test_is_bank_charge_slug_matches_per_account():
    from api.Modules.BankSync.Services import is_bank_charge_slug
    assert is_bank_charge_slug("bank_charge_210") is True
    assert is_bank_charge_slug("bank_charge_230") is True
    assert is_bank_charge_slug("bank_charge_9999") is True


def test_is_bank_charge_slug_rejects_other_slugs():
    from api.Modules.BankSync.Services import is_bank_charge_slug
    assert is_bank_charge_slug("cash_expense") is False
    assert is_bank_charge_slug("transfer_fee") is False
    # Looks-like-but-isn't
    assert is_bank_charge_slug("bankcharge") is False


def test_is_bank_charge_slug_handles_blank_and_none():
    from api.Modules.BankSync.Services import is_bank_charge_slug
    assert is_bank_charge_slug("") is False
    assert is_bank_charge_slug(None) is False


# ── builtin_substrings ─────────────────────────────────────


def test_builtin_substrings_returns_all_descriptions():
    """Helper for the rule-conflict UI."""
    from api.Modules.BankSync.Services import (
        BUILTIN_BANK_RULES, builtin_substrings,
    )
    expected = {sub for sub, _, _ in BUILTIN_BANK_RULES}
    assert builtin_substrings() == expected


# ── legacy Flask wrappers ──────────────────────────────────






