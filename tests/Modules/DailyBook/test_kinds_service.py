"""Unit tests for DailyBook.Services.kinds (PR 68)."""
import pytest


# ── registry shape ────────────────────────────────────────


def test_registry_contains_core_kinds():
    """Every kind that has live route + template support must
    appear in the registry — losing one silently breaks the
    daily-report widgets."""
    from api.Modules.DailyBook.Services import LINE_ITEM_KINDS
    expected = {
        "return_payback", "cash_purchase", "cash_expense",
        "check_purchase", "check_expense",
        "other_cash_in", "other_cash_out",
        "drop", "check_deposit",
    }
    assert expected.issubset(set(LINE_ITEM_KINDS.keys()))


def test_each_entry_is_three_tuple_of_strings():
    """The (field, singular, plural) contract is consumed by the
    flash messages + count renderers; surface a clear failure if
    a future edit drops a column."""
    from api.Modules.DailyBook.Services import LINE_ITEM_KINDS
    for kind, entry in LINE_ITEM_KINDS.items():
        assert isinstance(entry, tuple)
        assert len(entry) == 3
        for value in entry:
            assert isinstance(value, str)
            assert value, f"empty string in registry entry for {kind!r}"


def test_drop_uses_drops_plural():
    """Drops use 'drops' as the count unit — '3 drops', not
    '3 entries'. Same for check deposits."""
    from api.Modules.DailyBook.Services import LINE_ITEM_KINDS
    assert LINE_ITEM_KINDS["drop"][2] == "drops"
    assert LINE_ITEM_KINDS["check_deposit"][2] == "deposits"


def test_field_targets_match_dailyreport_columns():
    """The first tuple element is the `DailyReport` column name
    the kind rolls up into. Spot-check a few stable mappings."""
    from api.Modules.DailyBook.Services import LINE_ITEM_KINDS
    assert LINE_ITEM_KINDS["cash_expense"][0] == "cash_expense"
    assert LINE_ITEM_KINDS["drop"][0] == "outside_cash_drops"
    assert LINE_ITEM_KINDS["check_deposit"][0] == "checks_deposit"
    assert LINE_ITEM_KINDS["return_payback"][0] == "return_check_paid_back"


# ── helpers ────────────────────────────────────────────────


def test_is_known_kind_true_for_registered_kinds():
    from api.Modules.DailyBook.Services import is_known_kind
    assert is_known_kind("cash_expense") is True
    assert is_known_kind("drop") is True
    assert is_known_kind("check_deposit") is True


def test_is_known_kind_false_for_unknown():
    from api.Modules.DailyBook.Services import is_known_kind
    assert is_known_kind("not_a_kind") is False
    assert is_known_kind("") is False


def test_field_for_kind_returns_column_name():
    from api.Modules.DailyBook.Services import field_for_kind
    assert field_for_kind("cash_expense") == "cash_expense"
    assert field_for_kind("drop") == "outside_cash_drops"


def test_field_for_kind_none_for_unknown():
    from api.Modules.DailyBook.Services import field_for_kind
    assert field_for_kind("not_a_kind") is None


def test_all_kinds_iterable_includes_every_key():
    from api.Modules.DailyBook.Services import LINE_ITEM_KINDS, all_kinds
    listed = list(all_kinds())
    assert set(listed) == set(LINE_ITEM_KINDS.keys())


# ── kind_or_404 ────────────────────────────────────────────


def test_kind_or_404_returns_tuple_for_known():
    from api.Modules.DailyBook.Services import kind_or_404
    from app import app as flask_app
    with flask_app.test_request_context("/"):
        result = kind_or_404("cash_expense")
        assert result == ("cash_expense", "cash expense", "entries")


def test_kind_or_404_aborts_for_unknown():
    """Unknown kind → flask.abort(404). Tested by catching the
    HTTPException."""
    from werkzeug.exceptions import NotFound
    from api.Modules.DailyBook.Services import kind_or_404
    from app import app as flask_app
    with flask_app.test_request_context("/"):
        with pytest.raises(NotFound):
            kind_or_404("not_a_kind")


# ── legacy Flask wrappers ──────────────────────────────────


def test_legacy_constants_re_exported():
    from app import _LINE_ITEM_KINDS
    from api.Modules.DailyBook.Services import LINE_ITEM_KINDS
    assert _LINE_ITEM_KINDS is LINE_ITEM_KINDS


def test_legacy_kind_or_404_re_exported():
    from app import _line_item_kind_or_404
    from api.Modules.DailyBook.Services import kind_or_404
    assert _line_item_kind_or_404 is kind_or_404


def test_legacy_kind_or_404_returns_known():
    from app import app as flask_app, _line_item_kind_or_404
    with flask_app.test_request_context("/"):
        result = _line_item_kind_or_404("cash_expense")
        assert result[0] == "cash_expense"
