"""HTTP integration tests for the Stripe Financial Connections
lifecycle endpoints — replaces the dead /bank/stripe/* Flask
form-POST routes that went away in PR #550.

  POST /api/v2/bank/connect             — mint FC session
  POST /api/v2/bank/connect/complete    — persist FC accounts
  POST /api/v2/bank/disconnect/{id}     — soft-disconnect
  POST /api/v2/bank/refresh             — manual balance refresh
  POST /api/v2/bank/sync-transactions   — manual transaction sync

Every Stripe SDK call is patched so the suite has no network
egress.  Auth + cap enforcement + audit emission + tenancy
isolation are the actual contracts under test.
"""
from unittest.mock import patch, MagicMock

from tests._app import db, db_session


def _login(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_account(store_id, *, stripe_id="fcacc_seed", last4="9000",
                  disconnected=False):
    from datetime import datetime
    from api.Modules.BankSync.Models import StripeBankAccount
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=stripe_id,
        institution_name="Test Bank",
        display_name="Test Checking",
        last4=last4,
        enabled=not disconnected,
        disconnected_at=datetime.utcnow() if disconnected else None,
    )
    db.session.add(a); db.session.commit()
    return a.id


# ── Auth gating ─────────────────────────────────────────────


def test_connect_requires_jwt(client):
    resp = client.post("/api/v2/bank/connect", json={})
    assert resp.status_code == 401


def test_connect_rejects_employee(client, test_store_id):
    """Only admin / owner / superadmin can manage bank sync —
    cashiers (role=employee) get 403."""
    # Seed an employee user, log in as them.
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=test_store_id,
            username="cashier@test.com",
            full_name="Cashier",
            role="employee",
        )
        u.set_password("pw123!")
        db.session.add(u); db.session.commit()
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "cashier@test.com",
            "password": "pw123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.post(
        "/api/v2/bank/connect",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Cap enforcement ────────────────────────────────────────


def test_connect_409_when_at_account_cap(client, test_store_id):
    """6 active accounts is the per-store cap — the 7th /connect
    call returns 409 with a clear message."""
    with db_session():
        for i in range(6):
            _seed_account(
                test_store_id,
                stripe_id=f"fcacc_cap_{i}", last4=f"{i:04d}",
            )
    token = _login(client, test_store_id)
    with patch(
        "api.Modules.Billing.Services.customer.ensure_stripe_customer",
        return_value="cus_test_capped",
    ):
        resp = client.post(
            "/api/v2/bank/connect",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 409
    body = resp.get_json()
    assert "6" in body["detail"]


def test_connect_503_when_stripe_not_configured(
    client, test_store_id, monkeypatch,
):
    """Empty stripe.api_key surfaces as 503 with the friendly
    `Billing isn't configured` message — distinct from 502."""
    import stripe
    original = stripe.api_key
    try:
        stripe.api_key = ""  # type: ignore[assignment]
        token = _login(client, test_store_id)
        resp = client.post(
            "/api/v2/bank/connect",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503
        assert "STRIPE_SECRET_KEY" in resp.get_json()["detail"]
    finally:
        stripe.api_key = original


# ── Happy paths ────────────────────────────────────────────


def test_connect_returns_session_payload(client, test_store_id):
    """A clean connect mints an FC session via Stripe SDK and
    returns clientSecret + sessionId + publishableKey for the SPA
    to drive Stripe.js with."""
    token = _login(client, test_store_id)
    fake = MagicMock(
        client_secret="fcsec_test_abc", id="fcsess_test_abc",
    )
    with patch(
        "api.Modules.Billing.Services.customer.ensure_stripe_customer",
        return_value="cus_test_connect",
    ), patch(
        "stripe.financial_connections.Session.create",
        return_value=fake,
    ):
        resp = client.post(
            "/api/v2/bank/connect",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["clientSecret"] == "fcsec_test_abc"
    assert body["sessionId"] == "fcsess_test_abc"
    assert "publishableKey" in body


def test_connect_complete_upserts_accounts_and_audits(
    client, test_store_id,
):
    """`/connect/complete` reads the FC session, upserts each
    linked account, and writes a single connect_bank audit row."""
    from api.Modules.Audit.Models import OperatorAuditLog
    token = _login(client, test_store_id)

    # Fake the Stripe Session.retrieve to return 2 account objects.
    fake_accounts = MagicMock(data=[
        _fake_fc_account("fcacc_complete_1", "Chase", "1111"),
        _fake_fc_account("fcacc_complete_2", "Wells",  "2222"),
    ])
    fake_session = MagicMock(accounts=fake_accounts)
    with patch(
        "stripe.financial_connections.Session.retrieve",
        return_value=fake_session,
    ):
        resp = client.post(
            "/api/v2/bank/connect/complete",
            json={"sessionId": "fcsess_complete_test"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["accounts_added"] == 2

    audit = (
        db.session.query(OperatorAuditLog)
          .filter_by(
              store_id=test_store_id, action="connect_bank",
          )
          .order_by(OperatorAuditLog.id.desc())
          .first()
    )
    assert audit is not None
    assert "2 account" in (audit.summary or "")


def test_disconnect_account_soft_deletes_and_audits(client, test_store_id):
    """Disconnect flips enabled=False + sets disconnected_at +
    writes an audit row.  Historical txns are preserved."""
    from api.Modules.Audit.Models import OperatorAuditLog
    from api.Modules.BankSync.Models import StripeBankAccount
    aid = _seed_account(test_store_id, stripe_id="fcacc_to_drop", last4="7777")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/disconnect/{aid}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    row = db.session.get(StripeBankAccount, aid)
    assert row.enabled is False
    assert row.disconnected_at is not None
    audit = (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=test_store_id, action="disconnect_bank")
          .order_by(OperatorAuditLog.id.desc())
          .first()
    )
    assert audit is not None
    assert "7777" in (audit.summary or "")


def test_disconnect_account_404_cross_tenant(client, test_store_id):
    """Cross-tenant ids return opaque 404 — tenancy boundary."""
    from api.Modules.Tenancy.Models import Store
    other_aid: int = -1
    with db_session():
        other_store = Store(name="Other", slug="other-bank", plan="trial")
        db.session.add(other_store); db.session.flush()
        other_aid = _seed_account(
            other_store.id, stripe_id="fcacc_other", last4="0001",
        )
    # Log in as test_store admin; try to disconnect the OTHER store's account.
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/disconnect/{other_aid}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_refresh_calls_service_and_returns_count(client, test_store_id):
    token = _login(client, test_store_id)
    with patch(
        "api.Modules.BankSync.Services.fc_accounts.refresh_bank_balances",
        return_value=(3, ""),
    ):
        resp = client.post(
            "/api/v2/bank/refresh",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.get_json() == {"accounts_refreshed": 3, "error": ""}


def test_sync_transactions_returns_counts(client, test_store_id):
    token = _login(client, test_store_id)
    with patch(
        "api.Modules.BankSync.Services.sync.sync_bank_transactions",
        return_value=(5, 12, ""),
    ):
        resp = client.post(
            "/api/v2/bank/sync-transactions",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["new_rows"] == 5
    assert body["total_seen"] == 12
    assert body["error"] == ""


# ── Test helpers ───────────────────────────────────────────


def _fake_fc_account(stripe_id: str, institution: str, last4: str):
    """Mimic the shape `upsert_fc_account` reads from a Stripe FC
    Account object.  `_read()` in fc_accounts.py uses getattr / dict
    access so this needs to behave like both."""
    api_obj = MagicMock()
    api_obj.id = stripe_id
    api_obj.institution_name = institution
    api_obj.display_name = f"{institution} Checking"
    api_obj.last4 = last4
    api_obj.category = "checking"
    api_obj.subcategory = ""
    api_obj.status = "active"
    api_obj.balance = None
    return api_obj
