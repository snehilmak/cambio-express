"""Unit tests for SA Stripe-driven report services (PR 102):
refunds, failed_payments, payouts.
"""
from datetime import date
from unittest.mock import patch, MagicMock


class _FakePager:
    """Mimics the auto_paging_iter() return shape from stripe-python."""
    def __init__(self, items):
        self._items = items

    def auto_paging_iter(self):
        return iter(self._items)


def _list_call(items):
    """Return a callable that mimics `stripe.<X>.list(...)`."""
    pager = _FakePager(items)
    fn = MagicMock(return_value=pager)
    return fn


# ── refunds ─────────────────────────────────────────────


def test_refunds_groups_by_reason():
    """Refunds with same reason collapse to one bucket. Reasons
    are title-cased and underscores replaced with spaces."""
    from api.Modules.Superadmin.Services import refunds
    items = [
        {"amount": 1000, "reason": "duplicate"},
        {"amount": 2000, "reason": "duplicate"},
        {"amount":  500, "reason": "fraudulent"},
    ]
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Refund.list", _list_call(items)):
        rows, totals = refunds(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    by_reason = {r["reason"]: r for r in rows}
    assert by_reason["Duplicate"]["count"]  == 2
    assert by_reason["Duplicate"]["amount"] == 30.0
    assert by_reason["Fraudulent"]["count"] == 1
    assert totals["count"]  == 3
    assert totals["amount"] == 35.0
    assert totals["stripe_error"] == ""


def test_refunds_no_reason_renders_as_no_reason_label():
    from api.Modules.Superadmin.Services import refunds
    items = [{"amount": 1000, "reason": None}]
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Refund.list", _list_call(items)):
        rows, _ = refunds(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert rows[0]["reason"] == "(No Reason)"


def test_refunds_captures_stripe_error_in_totals():
    """When Stripe API fails, totals.stripe_error captures the
    exception type/message; rows return empty."""
    from api.Modules.Superadmin.Services import refunds
    fail_call = MagicMock(side_effect=RuntimeError("connection lost"))
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Refund.list", fail_call):
        rows, totals = refunds(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert rows == []
    assert "connection lost" in totals["stripe_error"]


def test_refunds_handles_no_stripe_key():
    from api.Modules.Superadmin.Services import refunds
    with patch("stripe.api_key", None):
        rows, totals = refunds(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert rows == []
    assert "Stripe API key not configured" in totals["stripe_error"]


# ── failed_payments ─────────────────────────────────────


def test_failed_payments_includes_only_failed_or_unpaid():
    """Charges with `status='failed'` OR `paid=False` are kept;
    successful paid charges are filtered out client-side."""
    from api.Modules.Superadmin.Services import failed_payments
    items = [
        {"amount": 1000, "status": "succeeded", "paid": True,
         "failure_message": ""},
        {"amount": 2000, "status": "failed", "paid": False,
         "outcome": {"reason": "card_declined"}},
        {"amount": 3000, "status": "failed", "paid": False,
         "outcome": {"reason": "card_declined"}},
    ]
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Charge.list", _list_call(items)):
        rows, totals = failed_payments(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert totals["count"] == 2
    assert totals["amount"] == 50.0
    assert rows[0]["reason"] == "card_declined"
    assert rows[0]["count"]  == 2


def test_failed_payments_truncates_long_reason():
    """Reason field truncated at 80 chars."""
    from api.Modules.Superadmin.Services import failed_payments
    long_reason = "x" * 200
    items = [{
        "amount": 100, "status": "failed", "paid": False,
        "outcome": {"reason": long_reason},
    }]
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Charge.list", _list_call(items)):
        rows, _ = failed_payments(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert len(rows[0]["reason"]) == 80


def test_failed_payments_falls_back_to_failure_message():
    """When `outcome.reason` is missing, fall back to
    `failure_message`."""
    from api.Modules.Superadmin.Services import failed_payments
    items = [{
        "amount": 100, "status": "failed", "paid": False,
        "failure_message": "expired_card",
    }]
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Charge.list", _list_call(items)):
        rows, _ = failed_payments(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert rows[0]["reason"] == "expired_card"


def test_failed_payments_captures_stripe_error():
    from api.Modules.Superadmin.Services import failed_payments
    fail_call = MagicMock(side_effect=RuntimeError("api down"))
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Charge.list", fail_call):
        rows, totals = failed_payments(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert rows == []
    assert "api down" in totals["stripe_error"]


# ── payouts ─────────────────────────────────────────────


def test_payouts_lists_each_payout_with_status_counts():
    from api.Modules.Superadmin.Services import payouts
    # 2026-05-15 12:00:00 UTC = 1778950800
    items = [
        {"id": "po_1", "amount": 50000, "status": "paid",
         "method": "standard", "arrival_date": 1778950800},
        {"id": "po_2", "amount": 25000, "status": "pending",
         "method": "instant", "arrival_date": 1778950800},
        {"id": "po_3", "amount": 10000, "status": "failed",
         "method": "standard", "arrival_date": 1778950800},
    ]
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Payout.list", _list_call(items)):
        rows, totals = payouts(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert len(rows) == 3
    statuses = {r["id"]: r["status"] for r in rows}
    assert statuses == {
        "po_1": "Paid", "po_2": "Pending", "po_3": "Failed",
    }
    assert totals["count"]  == 3
    assert totals["amount"] == 850.0
    assert totals["paid"]    == 1
    assert totals["pending"] == 1
    assert totals["failed"]  == 1


def test_payouts_method_underscore_replaced():
    from api.Modules.Superadmin.Services import payouts
    items = [{
        "id": "po_under", "amount": 1000, "status": "paid",
        "method": "standard_transfer", "arrival_date": 1778950800,
    }]
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Payout.list", _list_call(items)):
        rows, _ = payouts(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert rows[0]["method"] == "Standard Transfer"


def test_payouts_captures_stripe_error():
    from api.Modules.Superadmin.Services import payouts
    fail_call = MagicMock(side_effect=RuntimeError("rate limit"))
    with patch("stripe.api_key", "sk_test_dummy"), \
         patch("stripe.Payout.list", fail_call):
        rows, totals = payouts(
            db=None, d_from=date(2026, 5, 1), d_to=date(2026, 5, 31),
        )
    assert rows == []
    assert "rate limit" in totals["stripe_error"]


# ── legacy wrappers ──────────────────────────────────────






