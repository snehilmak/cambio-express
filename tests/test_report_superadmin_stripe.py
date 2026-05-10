"""Stripe-API-backed superadmin reports — Refunds, Failed Payments,
Payouts.

We don't hit Stripe in tests. Each data fn either:
  - finds STRIPE_SECRET_KEY unset and returns a stripe_error totals
    field surfaced by the template; or
  - is monkey-patched to return canned objects so we can verify the
    aggregation + KPI rendering path.
"""
from datetime import date, datetime
from unittest.mock import patch, MagicMock


def _superadmin_login(client):
    from app import User
    with client.application.app_context():
        sa_id = User.query.filter_by(role="superadmin").first().id
    with client.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"] = "superadmin"
        s["store_id"] = None


# ── Stripe API not configured: empty + diagnostic ────────────








# ── Mocked Stripe responses ──────────────────────────────────


def _fake_stripe_iter(items):
    """Mimic the .auto_paging_iter() returned by stripe list calls."""
    fake = MagicMock()
    fake.auto_paging_iter.return_value = iter(items)
    return fake








def test_refunds_csv_export(client):
    _superadmin_login(client)
    refunds = [
        {"id": "re_csv", "amount": 1000, "reason": "duplicate"},
    ]
    with patch("app.stripe.api_key", "sk_test_x"), \
         patch("app.stripe.Refund.list",
               return_value=_fake_stripe_iter(refunds)):
        resp = client.get("/superadmin/reports/refunds.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    body = resp.get_data(as_text=True)
    assert "Reason,Count,Amount" in body
    assert "Duplicate,1,10.00" in body
    assert "TOTAL,1,10.00" in body


def test_payouts_csv_export(client):
    _superadmin_login(client)
    arrival = int(datetime(2026, 5, 1).timestamp())
    payouts = [
        {"id": "po_csv", "amount": 200000, "status": "paid",
         "method": "standard", "arrival_date": arrival},
    ]
    with patch("app.stripe.api_key", "sk_test_x"), \
         patch("app.stripe.Payout.list",
               return_value=_fake_stripe_iter(payouts)):
        resp = client.get("/superadmin/reports/payouts.csv")
    body = resp.get_data(as_text=True)
    assert "Payout ID,Amount,Status,Method,Arrival" in body
    assert "po_csv,2000.00,Paid,Standard,2026-05-01" in body
    assert "TOTAL,2000.00" in body


# ── Auth ─────────────────────────────────────────────────────


def test_stripe_reports_require_superadmin(client, test_store_id):
    from app import User
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = test_store_id
    for slug in ("refunds", "failed-payments", "payouts"):
        resp = client.get(f"/superadmin/reports/{slug}",
                          follow_redirects=False)
        assert resp.status_code in (302, 303, 403), slug
