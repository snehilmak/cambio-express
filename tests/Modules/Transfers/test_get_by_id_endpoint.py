"""HTTP integration tests for GET /transfers/{transfer_id}."""
from datetime import date

from fastapi.testclient import TestClient


def _seed_transfer(store_id, *, send_amount=100.0, fee=2.0,
                    federal_tax=1.0, company="Intermex",
                    confirm_number=None):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
    t = Transfer(
        store_id=store_id, send_date=date.today(),
        company=company, service_type="Money Transfer",
        sender_name="S", recipient_name="R", country="MX",
        confirm_number=confirm_number or f"X{send_amount}",
        send_amount=send_amount, fee=fee, federal_tax=federal_tax,
        status="Sent",
    )
    db.session.add(t); db.session.commit()
    return t.id


def _client():
    from api.main import api_app
    return TestClient(api_app)


def test_get_transfer_returns_envelope(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        tid = _seed_transfer(
            test_store_id, send_amount=500.0,
            fee=5.0, federal_tax=2.0, company="Maxi",
        )
    resp = _client().get(
        f"/transfers/{tid}", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transfer"]["id"] == tid
    assert body["transfer"]["company"] == "Maxi"
    assert body["transfer"]["send_amount"] == 500.0
    assert body["transfer"]["total_collected"] == 507.0


def test_get_transfer_404_for_missing(test_store_id):
    resp = _client().get(
        "/transfers/99999",
        params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 404


def test_get_transfer_404_for_other_store(test_store_id):
    """Cross-tenant lookup returns 404 (never 403) so tenancy
    boundaries stay opaque."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-tx-get",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        tid = _seed_transfer(s2.id)
    resp = _client().get(
        f"/transfers/{tid}",
        params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 404


def test_get_transfer_requires_store_ids(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        tid = _seed_transfer(test_store_id)
    resp = _client().get(f"/transfers/{tid}")
    assert resp.status_code == 422


def test_get_transfer_rejects_zero_id(test_store_id):
    """Path validation: transfer_id must be ≥ 1."""
    resp = _client().get(
        "/transfers/0", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 422


def test_get_transfer_finds_in_umbrella_via_multi_store_ids(test_store_id):
    """`store_ids=1,2` finds a transfer in either store — same shape
    as the list endpoint."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-tx-umbrella",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        tid = _seed_transfer(sid2, send_amount=99.0)
    resp = _client().get(
        f"/transfers/{tid}",
        params={"store_ids": f"{test_store_id},{sid2}"},
    )
    assert resp.status_code == 200
    assert resp.json()["transfer"]["send_amount"] == 99.0


def test_openapi_includes_get_path():
    resp = _client().get("/openapi.json")
    paths = set(resp.json()["paths"].keys())
    assert "/transfers/{transfer_id}" in paths
