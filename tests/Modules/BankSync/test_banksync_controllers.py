"""HTTP integration tests for the BankSync Controllers.

After SPA-29 these endpoints derive `store_id` from the JWT
principal — explicit `store_ids` query params are gone. Tests
log in as the seeded admin and pass the resulting bearer token,
mirroring the ReturnChecks / Batches / Monthly test pattern.
"""
from datetime import datetime
from tests._app import db


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


def _seed_account(store_id, *, last4="0000", nickname=""):
    from api.Modules.BankSync.Models import StripeBankAccount
    from tests._app import db
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank",
        last4=last4,
        nickname=nickname,
    )
    db.session.add(a); db.session.commit()
    return a.id


def _seed_txn(store_id, account_id, *, amount_cents=-100,
              description="X", category_slug="",
              posted_at=None, stripe_transaction_id=None):
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import db
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=(
            stripe_transaction_id or f"t_{description}_{amount_cents}"
        ),
        amount_cents=amount_cents,
        description=description,
        category_slug=category_slug,
        posted_at=posted_at or datetime.utcnow(),
        status="posted",
    )
    db.session.add(t); db.session.commit()
    return t.id


# ── Auth gate ───────────────────────────────────────────────


def test_list_requires_jwt(client):
    resp = client.get("/api/v2/bank/transactions")
    assert resp.status_code == 401


def test_list_rejects_invalid_sign(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions?sign=garbage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_list_rejects_out_of_range_per_page(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions?per_page=1000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Happy paths ─────────────────────────────────────────────


def test_list_response_envelope(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id, nickname="Operating")
        _seed_txn(test_store_id, a, amount_cents=-100,
                  description="REMOTE DEPOSIT FEE")
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {
        "rows", "total", "page", "per_page", "total_pages",
        "page_total_cents", "uncategorized_count",
    }
    assert body["total"] == 1
    row = body["rows"][0]
    assert row["amount"] == -1.0
    assert row["amount_cents"] == -100
    assert row["account_label"] == "Operating"


def test_list_filters_by_account(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        a1 = _seed_account(test_store_id, last4="1111")
        a2 = _seed_account(test_store_id, last4="2222")
        _seed_txn(test_store_id, a1, description="A1")
        _seed_txn(test_store_id, a2, description="A2")
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/bank/transactions?account_id={a1}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    descs = {r["description"] for r in resp.get_json()["rows"]}
    assert descs == {"A1"}


def test_list_filters_by_sign(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, amount_cents=-100, description="DEBIT")
        _seed_txn(test_store_id, a, amount_cents=200, description="CREDIT")
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions?sign=credit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    descs = {r["description"] for r in resp.get_json()["rows"]}
    assert descs == {"CREDIT"}


def test_list_uncategorized_only_filter(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, description="UNTAGGED",
                  stripe_transaction_id="u")
        _seed_txn(
            test_store_id, a,
            description="TAGGED",
            category_slug="bank_charge_210",
            stripe_transaction_id="c",
        )
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions?uncategorized_only=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    descs = {r["description"] for r in resp.get_json()["rows"]}
    assert descs == {"UNTAGGED"}


def test_list_uncategorized_count_independent_of_filter(client, test_store_id):
    """`uncategorized_count` reflects every uncategorized row across
    the filter window, not just the rows matching `uncategorized_only`."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, description="U1",
                  stripe_transaction_id="u1")
        _seed_txn(test_store_id, a, description="U2",
                  stripe_transaction_id="u2")
        _seed_txn(
            test_store_id, a,
            description="C1",
            category_slug="bank_charge_210",
            stripe_transaction_id="c1",
        )
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions?category_slug=bank_charge_210",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    assert body["total"] == 1
    assert body["uncategorized_count"] == 2


def test_list_pagination(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        for i in range(5):
            _seed_txn(test_store_id, a, description=f"T{i}",
                      stripe_transaction_id=f"t{i}")
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions?page=1&per_page=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert len(body["rows"]) == 2


# ── Cross-tenant safety ─────────────────────────────────────


def test_list_scoped_to_principal_store(client, test_store_id):
    """Even if a sibling store has transactions, the JWT-scoped list
    only sees the principal's store. Confirms that the dropped
    `store_ids` query param can't be smuggled back in via the URL."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, description="MINE",
                  stripe_transaction_id="mine")
        # Sibling store with its own account + txn
        other = Store(name="Other", slug="other-store", plan="trial")
        db.session.add(other); db.session.commit()
        other_id = other.id
        b = _seed_account(other_id, last4="9999")
        _seed_txn(other_id, b, description="THEIRS",
                  stripe_transaction_id="theirs")
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    descs = {r["description"] for r in resp.get_json()["rows"]}
    assert descs == {"MINE"}


# ── OpenAPI shape ───────────────────────────────────────────


def test_openapi_includes_bank_path(client):
    resp = client.get("/api/v2/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.get_json()["paths"].keys())
    assert "/bank/transactions" in paths
