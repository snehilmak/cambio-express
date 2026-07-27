"""Superadmin Stripe account-credit (PR B).

Two layers:

* Service unit tests (``issue_store_credit``) — Stripe SDK stubbed via
  monkeypatch, same technique as the referral-credit tests. Proves the
  amount is negated, the guardrails fire, and each failure mode raises
  the right typed exception.
* Endpoint tests (``POST /superadmin/stores/{id}/credit``) — happy
  path with Stripe stubbed, the 404 / 409 / 422 / 503 branches, the
  auth gate, and the audit-row assertion (invariant #7).
"""
from unittest.mock import MagicMock

import pytest

from tests._app import db, db_session
from tests.conftest import login_superadmin


@pytest.fixture
def sa_headers(client):
    return {"Authorization": f"Bearer {login_superadmin(client)}"}


def _stub_stripe(monkeypatch, *, txn_id="txn_1", error=None):
    """Configure the Stripe SDK key + stub create_balance_transaction.
    Returns the mock so callers can assert on the call args."""
    import stripe
    monkeypatch.setattr(stripe, "api_key", "sk_test_dummy", raising=False)
    if error is not None:
        fn = MagicMock(side_effect=error)
    else:
        fn = MagicMock(return_value=MagicMock(id=txn_id))
    monkeypatch.setattr(stripe.Customer, "create_balance_transaction", fn)
    return fn


def _store(customer="cus_x", store_id=7):
    s = MagicMock()
    s.id = store_id
    s.stripe_customer_id = customer
    return s


# ── Service unit tests ─────────────────────────────────────


def test_issue_credit_posts_negative_amount(monkeypatch):
    from api.Modules.Billing.Services import issue_store_credit
    fn = _stub_stripe(monkeypatch, txn_id="txn_OK")
    txn = issue_store_credit(
        MagicMock(), _store(), 5000, reason="downtime",
        superadmin_username="root",
    )
    assert txn == "txn_OK"
    # Positive request → negative balance transaction (a credit).
    assert fn.call_args.kwargs["amount"] == -5000
    assert fn.call_args.kwargs["currency"] == "usd"
    # Customer id is the first positional arg.
    assert fn.call_args.args[0] == "cus_x"


def test_issue_credit_rejects_zero(monkeypatch):
    from api.Modules.Billing.Services import (
        InvalidCreditAmountError, issue_store_credit,
    )
    with pytest.raises(InvalidCreditAmountError):
        issue_store_credit(MagicMock(), _store(), 0)


def test_issue_credit_rejects_over_max(monkeypatch):
    from api.Modules.Billing.Services import (
        InvalidCreditAmountError, MAX_CREDIT_CENTS, issue_store_credit,
    )
    with pytest.raises(InvalidCreditAmountError):
        issue_store_credit(MagicMock(), _store(), MAX_CREDIT_CENTS + 1)


def test_issue_credit_requires_stripe_customer(monkeypatch):
    from api.Modules.Billing.Services import issue_store_credit
    from api.Modules.Billing.Services.portal import NoBillingCustomerError
    _stub_stripe(monkeypatch)
    with pytest.raises(NoBillingCustomerError):
        issue_store_credit(MagicMock(), _store(customer=""), 5000)


def test_issue_credit_raises_when_not_configured(monkeypatch):
    import stripe
    from api.Modules.Billing.Services import issue_store_credit
    from api.Modules.Billing.Services.config import StripeNotConfiguredError
    monkeypatch.setattr(stripe, "api_key", "", raising=False)
    with pytest.raises(StripeNotConfiguredError):
        issue_store_credit(MagicMock(), _store(), 5000)


def test_issue_credit_wraps_stripe_error(monkeypatch):
    import stripe
    from api.Modules.Billing.Services import (
        StripeServiceError, issue_store_credit,
    )
    _stub_stripe(monkeypatch, error=stripe.error.StripeError("boom"))
    with pytest.raises(StripeServiceError):
        issue_store_credit(MagicMock(), _store(), 5000)


# ── Endpoint tests ─────────────────────────────────────────


def _set_customer(store_id, customer="cus_test"):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = db.session.get(Store, store_id)
        s.stripe_customer_id = customer
        db.session.commit()


def test_credit_happy_path(client, sa_headers, test_store_id, monkeypatch):
    _set_customer(test_store_id)
    fn = _stub_stripe(monkeypatch, txn_id="txn_ep")
    resp = client.post(
        f"/api/v2/superadmin/stores/{test_store_id}/credit",
        json={"amount_cents": 5000, "reason": "make-good"},
        headers=sa_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["amount_cents"] == 5000
    assert body["stripe_txn_id"] == "txn_ep"
    assert fn.call_args.kwargs["amount"] == -5000


def test_credit_writes_audit_entry(client, sa_headers, test_store_id, monkeypatch):
    from api.Modules.Audit.Models import SuperadminAuditLog
    _set_customer(test_store_id)
    _stub_stripe(monkeypatch)
    with db_session():
        before = db.session.query(SuperadminAuditLog).count()
    resp = client.post(
        f"/api/v2/superadmin/stores/{test_store_id}/credit",
        json={"amount_cents": 2500, "reason": "downtime"},
        headers=sa_headers,
    )
    assert resp.status_code == 200
    with db_session():
        after = db.session.query(SuperadminAuditLog).count()
        assert after == before + 1
        last = (
            db.session.query(SuperadminAuditLog)
              .order_by(SuperadminAuditLog.id.desc())
              .first()
        )
        assert last.action == "credit_store"
        assert last.target_id == str(test_store_id)


def test_credit_409_when_no_stripe_customer(
    client, sa_headers, test_store_id, monkeypatch,
):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = db.session.get(Store, test_store_id)
        s.stripe_customer_id = None
        db.session.commit()
    _stub_stripe(monkeypatch)
    resp = client.post(
        f"/api/v2/superadmin/stores/{test_store_id}/credit",
        json={"amount_cents": 5000},
        headers=sa_headers,
    )
    assert resp.status_code == 409


def test_credit_503_when_stripe_not_configured(
    client, sa_headers, test_store_id, monkeypatch,
):
    import stripe
    _set_customer(test_store_id)
    monkeypatch.setattr(stripe, "api_key", "", raising=False)
    resp = client.post(
        f"/api/v2/superadmin/stores/{test_store_id}/credit",
        json={"amount_cents": 5000},
        headers=sa_headers,
    )
    assert resp.status_code == 503


def test_credit_422_on_zero_amount(client, sa_headers, test_store_id):
    resp = client.post(
        f"/api/v2/superadmin/stores/{test_store_id}/credit",
        json={"amount_cents": 0},
        headers=sa_headers,
    )
    assert resp.status_code == 422


def test_credit_422_over_max(client, sa_headers, test_store_id):
    resp = client.post(
        f"/api/v2/superadmin/stores/{test_store_id}/credit",
        json={"amount_cents": 500_001},
        headers=sa_headers,
    )
    assert resp.status_code == 422


def test_credit_404_unknown_store(client, sa_headers, monkeypatch):
    _stub_stripe(monkeypatch)
    resp = client.post(
        "/api/v2/superadmin/stores/9999999/credit",
        json={"amount_cents": 5000},
        headers=sa_headers,
    )
    assert resp.status_code == 404


def test_credit_requires_superadmin(client, test_store_id):
    resp = client.post(
        f"/api/v2/superadmin/stores/{test_store_id}/credit",
        json={"amount_cents": 5000},
    )
    assert resp.status_code in (401, 403)
