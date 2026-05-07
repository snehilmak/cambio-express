"""HTTP integration tests for the BankSync Controllers (PR 16)."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def _seed_account(store_id, *, last4="0000", nickname=""):
    from app import StripeBankAccount, db
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
    from app import BankTransaction, db
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


def _client():
    from api.main import api_app
    return TestClient(api_app)


# ── Validation ──────────────────────────────────────────────


def test_list_requires_store_ids():
    resp = _client().get("/bank/transactions")
    assert resp.status_code == 422


def test_list_rejects_invalid_sign():
    resp = _client().get(
        "/bank/transactions",
        params={"store_ids": "1", "sign": "garbage"},
    )
    assert resp.status_code == 422


def test_list_rejects_out_of_range_per_page():
    resp = _client().get(
        "/bank/transactions",
        params={"store_ids": "1", "per_page": 1000},
    )
    assert resp.status_code == 422


# ── Happy paths ─────────────────────────────────────────────


def test_list_response_envelope(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id, nickname="Operating")
        _seed_txn(test_store_id, a, amount_cents=-100,
                    description="REMOTE DEPOSIT FEE")
    resp = _client().get(
        "/bank/transactions", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "rows", "total", "page", "per_page", "total_pages",
        "page_total_cents", "uncategorized_count",
    }
    assert body["total"] == 1
    row = body["rows"][0]
    assert row["amount"] == -1.0
    assert row["amount_cents"] == -100
    assert row["account_label"] == "Operating"


def test_list_filters_by_account(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a1 = _seed_account(test_store_id, last4="1111")
        a2 = _seed_account(test_store_id, last4="2222")
        _seed_txn(test_store_id, a1, description="A1")
        _seed_txn(test_store_id, a2, description="A2")
    resp = _client().get(
        "/bank/transactions",
        params={"store_ids": str(test_store_id), "account_id": str(a1)},
    )
    assert resp.status_code == 200
    descs = {r["description"] for r in resp.json()["rows"]}
    assert descs == {"A1"}


def test_list_filters_by_sign(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, amount_cents=-100, description="DEBIT")
        _seed_txn(test_store_id, a, amount_cents=200, description="CREDIT")
    resp = _client().get(
        "/bank/transactions",
        params={"store_ids": str(test_store_id), "sign": "credit"},
    )
    assert resp.status_code == 200
    descs = {r["description"] for r in resp.json()["rows"]}
    assert descs == {"CREDIT"}


def test_list_uncategorized_only_filter(test_store_id):
    from app import app as flask_app
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
    resp = _client().get(
        "/bank/transactions",
        params={
            "store_ids": str(test_store_id),
            "uncategorized_only": "true",
        },
    )
    assert resp.status_code == 200
    descs = {r["description"] for r in resp.json()["rows"]}
    assert descs == {"UNTAGGED"}


def test_list_uncategorized_count_independent_of_filter(test_store_id):
    """`uncategorized_count` reflects every uncategorized row across
    the filter window, not just the rows matching `uncategorized_only`."""
    from app import app as flask_app
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
    # Caller filters by category_slug — the response total is 1, but
    # uncategorized_count must still report the 2 uncategorized rows.
    resp = _client().get(
        "/bank/transactions",
        params={
            "store_ids": str(test_store_id),
            "category_slug": "bank_charge_210",
        },
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["uncategorized_count"] == 2


def test_list_pagination(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        for i in range(5):
            _seed_txn(test_store_id, a, description=f"T{i}",
                       stripe_transaction_id=f"t{i}")
    resp = _client().get(
        "/bank/transactions",
        params={
            "store_ids": str(test_store_id),
            "page": 1, "per_page": 2,
        },
    )
    body = resp.json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert len(body["rows"]) == 2


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_bank_to_fastapi(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, description="VIA-FLASK")
    resp = client.get(
        f"/api/v2/bank/transactions?store_ids={test_store_id}",
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["total"] == 1


def test_openapi_includes_bank_path():
    resp = _client().get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/bank/transactions" in paths
