"""HTTP integration tests for the BankSync write-side endpoints.

  POST /api/v2/bank/transactions/{txn_id}/categorize
  POST /api/v2/bank/transactions/{txn_id}/uncategorize

Both go through the existing `categorize_transaction` /
`uncategorize_transaction` Services so the daily-book mirror
behavior is shared with the legacy Flask handlers.
"""
from datetime import datetime


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


def _seed_account(store_id, *, last4="0000"):
    from api.Modules.BankSync.Models import StripeBankAccount
    from app import db
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank",
        last4=last4,
    )
    db.session.add(a); db.session.commit()
    return a.id


def _seed_txn(store_id, account_id, *, amount_cents=-100,
              description="X", category_slug="",
              stripe_transaction_id=None):
    from api.Modules.BankSync.Models import BankTransaction
    from app import db
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=(
            stripe_transaction_id or f"t_{description}_{amount_cents}"
        ),
        amount_cents=amount_cents,
        description=description,
        category_slug=category_slug,
        posted_at=datetime.utcnow(),
        status="posted",
    )
    db.session.add(t); db.session.commit()
    return t.id


# ── Auth gating ─────────────────────────────────────────────


def test_categorize_requires_jwt(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        tid = _seed_txn(test_store_id, a)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/categorize",
        json={"target_kind": "bank_charge_210"},
    )
    assert resp.status_code == 401


def test_uncategorize_requires_jwt(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        tid = _seed_txn(test_store_id, a)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/uncategorize",
    )
    assert resp.status_code == 401


# ── Schema validation ───────────────────────────────────────


def test_categorize_rejects_missing_target_kind(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        tid = _seed_txn(test_store_id, a)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/categorize",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_categorize_rejects_extra_fields(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        tid = _seed_txn(test_store_id, a)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/categorize",
        json={"target_kind": "bank_charge_210", "rogue": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Happy paths ─────────────────────────────────────────────


def test_categorize_assigns_kind_and_returns_row(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        tid = _seed_txn(test_store_id, a, description="REMOTE DEPOSIT FEE")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/categorize",
        json={"target_kind": "bank_charge_210", "post_to_daily": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["transaction"]["category_slug"] == "bank_charge_210"
    assert body["transaction"]["id"] == tid


def test_uncategorize_clears_kind(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        tid = _seed_txn(
            test_store_id, a,
            category_slug="bank_charge_210",
        )
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/uncategorize",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["transaction"]["category_slug"] == ""


def test_categorize_idempotent_replaces_prior_kind(client, test_store_id):
    """Re-categorizing should overwrite the prior slug, not stack it."""
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        tid = _seed_txn(
            test_store_id, a,
            category_slug="bank_charge_210",
        )
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/categorize",
        json={"target_kind": "bank_charge_230", "post_to_daily": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["transaction"]["category_slug"] == "bank_charge_230"


# ── Cross-tenant safety ─────────────────────────────────────


def test_categorize_rejects_other_stores_txn(client, test_store_id):
    """A txn that belongs to a different store must 404, not 200."""
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    with flask_app.app_context():
        other = Store(name="Other", slug="other-bs", plan="trial")
        db.session.add(other); db.session.commit()
        oid = other.id
        a = _seed_account(oid)
        tid = _seed_txn(oid, a)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/transactions/{tid}/categorize",
        json={"target_kind": "bank_charge_210"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_categorize_404_when_txn_missing(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/transactions/999999/categorize",
        json={"target_kind": "bank_charge_210"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
