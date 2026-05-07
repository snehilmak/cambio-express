"""HTTP integration tests for /bank/accounts (PR 26)."""
from datetime import datetime

from fastapi.testclient import TestClient


def _seed_account(store_id, *, last4="0000", nickname="",
                    display_name="", institution_name="Bank",
                    enabled=True):
    from app import StripeBankAccount, db
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacc_{last4}_{nickname or display_name or institution_name}",
        institution_name=institution_name,
        display_name=display_name,
        nickname=nickname,
        last4=last4,
        enabled=enabled,
        last_balance_cents=12345,
        last_balance_as_of=datetime.utcnow(),
    )
    db.session.add(a); db.session.commit()
    return a.id


def _client():
    from api.main import api_app
    return TestClient(api_app)


def test_accounts_endpoint_requires_store_ids():
    resp = _client().get("/bank/accounts")
    assert resp.status_code == 422


def test_accounts_endpoint_returns_empty_envelope(test_store_id):
    resp = _client().get(
        "/bank/accounts", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    assert resp.json() == {"rows": [], "total": 0}


def test_accounts_endpoint_returns_label_and_balance(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_account(
            test_store_id, last4="9999", nickname="Operating",
        )
    resp = _client().get(
        "/bank/accounts", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    row = body["rows"][0]
    assert row["nickname"] == "Operating"
    assert row["last4"] == "9999"
    assert row["label"] == "Operating"
    assert row["last_balance_cents"] == 12345
    assert row["last_balance"] == 123.45


def test_accounts_endpoint_label_falls_back_to_last4(test_store_id):
    """No nickname → label = ••last4."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_account(test_store_id, last4="1234")
    resp = _client().get(
        "/bank/accounts", params={"store_ids": str(test_store_id)},
    )
    body = resp.json()
    assert body["rows"][0]["label"] == "••1234"


def test_accounts_endpoint_orders_by_label(test_store_id):
    """Repository orders by nickname → display_name → institution_name
    (case-insensitive). Z before a should sort a first."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_account(
            test_store_id, last4="2", nickname="Zebra",
        )
        _seed_account(
            test_store_id, last4="1", nickname="alpha",
        )
    resp = _client().get(
        "/bank/accounts", params={"store_ids": str(test_store_id)},
    )
    nicknames = [r["nickname"] for r in resp.json()["rows"]]
    assert nicknames == ["alpha", "Zebra"]


def test_accounts_endpoint_includes_disconnected(test_store_id):
    """Both enabled and disconnected accounts return — clients filter
    via the `enabled` field if they want only active ones."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_account(test_store_id, last4="ON", enabled=True)
        _seed_account(test_store_id, last4="OFF", enabled=False)
    resp = _client().get(
        "/bank/accounts", params={"store_ids": str(test_store_id)},
    )
    body = resp.json()
    assert body["total"] == 2
    by_last4 = {r["last4"]: r for r in body["rows"]}
    assert by_last4["ON"]["enabled"] is True
    assert by_last4["OFF"]["enabled"] is False


def test_accounts_endpoint_excludes_other_stores(test_store_id):
    from app import app as flask_app, Store, db
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-bank-acc",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_account(s2.id, last4="HIDDEN")
    resp = _client().get(
        "/bank/accounts", params={"store_ids": str(test_store_id)},
    )
    assert resp.json()["rows"] == []


def test_openapi_includes_accounts_path():
    resp = _client().get("/openapi.json")
    paths = set(resp.json()["paths"].keys())
    assert "/bank/accounts" in paths
