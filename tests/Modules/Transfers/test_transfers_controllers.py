"""HTTP integration tests for the Transfers Controllers (PR 12).

Tests hit the FastAPI router via TestClient + via the Flask dispatcher
(strangler-fig path).
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient


def _seed_transfer(store_id, *, send_date=None, send_amount=100.0,
                    fee=2.0, federal_tax=1.0, company="Intermex",
                    service_type="Money Transfer", country="MX",
                    sender_name="S", recipient_name="R",
                    confirm_number=None, status="Sent",
                    batch_id=""):
    from app import Transfer, db
    t = Transfer(
        store_id=store_id,
        send_date=send_date or date.today(),
        company=company,
        service_type=service_type,
        sender_name=sender_name,
        recipient_name=recipient_name,
        country=country,
        confirm_number=confirm_number or f"X{send_amount}-{recipient_name}",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
        batch_id=batch_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _client():
    from api.main import api_app
    return TestClient(api_app)


# ── parse_store_ids contract ────────────────────────────────


def test_list_requires_store_ids():
    resp = _client().get("/transfers")
    assert resp.status_code == 422


def test_list_rejects_non_numeric_store_ids():
    resp = _client().get("/transfers", params={"store_ids": "abc"})
    assert resp.status_code == 422


def test_list_rejects_empty_store_ids():
    resp = _client().get("/transfers", params={"store_ids": ""})
    assert resp.status_code == 422


def test_list_rejects_invalid_dir():
    resp = _client().get(
        "/transfers", params={"store_ids": "1", "dir": "garbage"},
    )
    assert resp.status_code == 422


def test_list_rejects_out_of_range_per_page():
    resp = _client().get(
        "/transfers", params={"store_ids": "1", "per_page": 0},
    )
    assert resp.status_code == 422
    resp = _client().get(
        "/transfers", params={"store_ids": "1", "per_page": 1000},
    )
    assert resp.status_code == 422


# ── Happy paths ─────────────────────────────────────────────


def test_list_response_envelope(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        for i in range(3):
            _seed_transfer(test_store_id, send_amount=100.0)
    resp = _client().get(
        "/transfers", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "rows", "total", "page", "per_page", "total_pages", "page_amount",
    }
    assert body["total"] == 3
    assert len(body["rows"]) == 3


def test_list_filters_company(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, company="Intermex",
                        confirm_number="X-Intermex")
        _seed_transfer(test_store_id, company="Maxi",
                        confirm_number="X-Maxi")
    resp = _client().get(
        "/transfers",
        params={"store_ids": str(test_store_id), "company": "Maxi"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["rows"][0]["company"] == "Maxi"


def test_list_global_search_q(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, sender_name="Alice",
                        confirm_number="X-A")
        _seed_transfer(test_store_id, sender_name="Bob",
                        confirm_number="X-B")
    resp = _client().get(
        "/transfers",
        params={"store_ids": str(test_store_id), "q": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_list_pagination(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        for i in range(5):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1))
    resp = _client().get(
        "/transfers",
        params={"store_ids": str(test_store_id), "per_page": 2, "page": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert body["page"] == 1
    assert len(body["rows"]) == 2


def test_list_filters_date_range_string_input(test_store_id):
    """Controller takes `date_from`/`date_to` as YYYY-MM-DD strings;
    the underlying TransferFilters parses them. Malformed strings drop
    the filter (legacy behavior)."""
    from app import app as flask_app
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_date=last_week,
                        confirm_number="X-LW")
        _seed_transfer(test_store_id, send_date=today,
                        confirm_number="X-T")
    resp = _client().get(
        "/transfers",
        params={
            "store_ids": str(test_store_id),
            "date_from": yesterday.isoformat(),
            "date_to": today.isoformat(),
        },
    )
    assert resp.status_code == 200
    confirms = {r["confirm_number"] for r in resp.json()["rows"]}
    assert confirms == {"X-T"}


def test_list_multi_store_aggregation(test_store_id):
    from app import app as flask_app, Store, db
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-tx-cc",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        _seed_transfer(test_store_id, confirm_number="X-Mine")
        _seed_transfer(sid2, confirm_number="X-Theirs")
    resp = _client().get(
        "/transfers",
        params={"store_ids": f"{test_store_id},{sid2}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_list_rows_have_total_collected(test_store_id):
    """Wire test: the row payload must include `total_collected`
    (send + fee + tax) so the React table can render the column
    without recomputing client-side."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0,
                        fee=2.0, federal_tax=1.0)
    resp = _client().get(
        "/transfers", params={"store_ids": str(test_store_id)},
    )
    body = resp.json()
    assert body["rows"][0]["total_collected"] == 103.0


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_transfers_to_fastapi(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=99.0)
    resp = client.get(
        f"/api/v2/transfers?store_ids={test_store_id}",
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["total"] == 1


def test_openapi_includes_transfers_path():
    resp = _client().get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/transfers" in paths
