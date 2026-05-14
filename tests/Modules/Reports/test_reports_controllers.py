"""HTTP integration tests for the Reports Controllers (PR 4).

These exercise the FastAPI router via two surfaces:

  1. `TestClient(api_app)` — direct hits to FastAPI without the
     dispatcher. Route paths are relative (`/reports/...`).
  2. The Flask test client through `DispatcherMiddleware` — proves
     the strangler-fig wiring still routes `/api/v2/reports/*` into
     FastAPI in the live app.

Service-level behavior (sort order, walk-in bucketing, FK
resolution, etc.) is already covered by `test_sales_services.py`
and `test_employee_services.py`; this file just pins the
controller contract: query parsing, response envelope shape, and
status codes.
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient


def _seed_transfer(store_id, *, send_amount=100.0, fee=2.0,
                    federal_tax=1.0, company="Intermex",
                    service_type="Money Transfer", country="MX",
                    recipient_name="R", status="Sent",
                    created_by=None, employee_id=None,
                    customer_id=None, send_date=None):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
    t = Transfer(
        store_id=store_id,
        send_date=send_date or date.today(),
        company=company,
        service_type=service_type,
        sender_name="S",
        recipient_name=recipient_name,
        country=country,
        confirm_number=f"X{send_amount}-{recipient_name}",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
        created_by=created_by,
        employee_id=employee_id,
        customer_id=customer_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _client():
    from api.main import api_app
    return TestClient(api_app)


# ── parse_period / parse_store_ids dependency contracts ─────


def test_store_ids_required_returns_422(test_store_id):
    """`store_ids` is a required Query — missing it must 422."""
    resp = _client().get("/reports/sales-by-company")
    assert resp.status_code == 422


def test_store_ids_non_numeric_returns_422(test_store_id):
    resp = _client().get(
        "/reports/sales-by-company", params={"store_ids": "abc,def"},
    )
    assert resp.status_code == 422


def test_store_ids_empty_string_returns_422(test_store_id):
    resp = _client().get(
        "/reports/sales-by-company", params={"store_ids": ""},
    )
    assert resp.status_code == 422


def test_period_swaps_when_from_after_to(test_store_id):
    """Mirrors `_report_period`: if the caller passes `from > to`,
    the dependency swaps them so the SQL window is non-empty."""
    from tests._app import app as flask_app
    today = date.today()
    yesterday = today - timedelta(days=1)
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, send_date=yesterday)
    resp = _client().get(
        "/reports/sales-by-company",
        params={
            "store_ids": str(test_store_id),
            "from": today.isoformat(),
            "to": yesterday.isoformat(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # Yesterday's row should be inside the (swapped) window.
    assert body["totals"]["sent"] == 100.0


def test_period_falls_back_to_defaults_on_garbage_input(test_store_id):
    """`_report_period` swallows ValueError and falls back to today /
    first-of-month. The dependency mirrors that."""
    from tests._app import app as flask_app
    today = date.today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=42.0)
    resp = _client().get(
        "/reports/sales-by-company",
        params={
            "store_ids": str(test_store_id),
            "from": "not-a-date",
            "to": "also-not-a-date",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["sent"] == 42.0


# ── Per-route happy-path response envelopes ─────────────────


def test_sales_by_company_envelope(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, company="Intermex")
        _seed_transfer(test_store_id, send_amount=300.0, company="Maxi")
    resp = _client().get(
        "/reports/sales-by-company",
        params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"rows", "totals"}
    companies = {r["company"] for r in body["rows"]}
    assert companies == {"Intermex", "Maxi"}
    assert body["totals"]["sent"] == 400.0


def test_sales_by_service_envelope(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0,
                        service_type="Money Transfer")
        _seed_transfer(test_store_id, send_amount=200.0,
                        service_type="Bill Payment")
    resp = _client().get(
        "/reports/sales-by-service",
        params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    types = {r["service_type"] for r in body["rows"]}
    assert types == {"Money Transfer", "Bill Payment"}


def test_by_destination_country_envelope(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, country="MX")
        _seed_transfer(test_store_id, send_amount=200.0, country="GT")
    resp = _client().get(
        "/reports/by-destination-country",
        params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    countries = {r["country"] for r in body["rows"]}
    assert countries == {"MX", "GT"}


def test_top_recipients_respects_limit_query_param(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        for i in range(5):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1),
                            recipient_name=f"R{i}")
    resp = _client().get(
        "/reports/top-recipients",
        params={"store_ids": str(test_store_id), "limit": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 2
    # Totals span every row, not just the top 2.
    assert body["totals"]["sent"] == 1500.0


def test_top_recipients_rejects_out_of_range_limit(test_store_id):
    """`limit` is bounded `[1, 500]` — out-of-range values 422."""
    resp = _client().get(
        "/reports/top-recipients",
        params={"store_ids": str(test_store_id), "limit": 0},
    )
    assert resp.status_code == 422
    resp = _client().get(
        "/reports/top-recipients",
        params={"store_ids": str(test_store_id), "limit": 501},
    )
    assert resp.status_code == 422


def test_top_customers_respects_sort_by(test_store_id):
    from api.Modules.Customers.Models import Customer
    from tests._app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        c = Customer(
            store_id=test_store_id, full_name="Alice",
            phone_country="+1", phone_number="5551234",
        )
        db.session.add(c); db.session.commit()
        cid = c.id
        _seed_transfer(
            test_store_id, send_amount=500.0, customer_id=cid,
            recipient_name="R1",
        )
    resp = _client().get(
        "/reports/top-customers",
        params={"store_ids": str(test_store_id), "sort_by": "sent"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"][0]["customer"] == "Alice"
    assert body["rows"][0]["phone"] == "+15551234"


def test_top_customers_rejects_invalid_sort_by(test_store_id):
    """`sort_by` is regex-restricted to `sent|count`."""
    resp = _client().get(
        "/reports/top-customers",
        params={"store_ids": str(test_store_id), "sort_by": "garbage"},
    )
    assert resp.status_code == 422


def test_sales_by_employee_resolves_user(test_store_id):
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        u = User(
            store_id=test_store_id, username="cash@x.com",
            full_name="Cash Cashier", role="employee",
        )
        u.set_password("p")
        db.session.add(u); db.session.commit()
        uid = u.id
        _seed_transfer(test_store_id, created_by=uid, send_amount=300.0)
    resp = _client().get(
        "/reports/sales-by-employee",
        params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"][0]["employee"] == "Cash Cashier"
    assert body["rows"][0]["username"] == "cash@x.com"


def test_cashier_productivity_resolves_storeemployee(test_store_id):
    from api.Modules.Tenancy.Models import StoreEmployee
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        e = StoreEmployee(
            store_id=test_store_id, name="Maria", is_active=True,
        )
        db.session.add(e); db.session.commit()
        eid = e.id
        _seed_transfer(test_store_id, employee_id=eid, send_amount=50.0)
    resp = _client().get(
        "/reports/cashier-productivity",
        params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"][0]["cashier"] == "Maria"
    assert body["rows"][0]["is_active"] is True


# ── Multi-store + period filtering through the controller ──


def test_store_ids_multi_value_aggregates_across_stores(test_store_id):
    """Comma-separated `store_ids=1,2` must aggregate across both."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-store",
                    email="o@test.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        _seed_transfer(test_store_id, send_amount=100.0)
        _seed_transfer(sid2, send_amount=200.0)
    resp = _client().get(
        "/reports/sales-by-company",
        params={"store_ids": f"{test_store_id},{sid2}"},
    )
    assert resp.status_code == 200
    assert resp.json()["totals"]["sent"] == 300.0


def test_period_filter_excludes_out_of_range_rows(test_store_id):
    from tests._app import app as flask_app
    today = date.today()
    last_year = today - timedelta(days=365)
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, send_date=last_year)
        _seed_transfer(test_store_id, send_amount=200.0, send_date=today)
    resp = _client().get(
        "/reports/sales-by-company",
        params={
            "store_ids": str(test_store_id),
            "from": today.isoformat(),
            "to": today.isoformat(),
        },
    )
    assert resp.status_code == 200
    # Only today's row is in the window.
    assert resp.json()["totals"]["sent"] == 200.0


# ── Strangler-fig dispatch via Flask ────────────────────────


def test_flask_dispatcher_routes_reports_to_fastapi(client, test_store_id):
    """The DispatcherMiddleware must forward `/api/v2/reports/*` into
    FastAPI. Hitting one route is enough to pin the wiring; the
    standalone TestClient cases above cover route logic."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=99.0, company="Intermex")
    resp = client.get(
        f"/api/v2/reports/sales-by-company?store_ids={test_store_id}",
    )
    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    assert body["totals"]["sent"] == 99.0


def test_openapi_includes_reports_paths():
    """Sanity check: the FastAPI OpenAPI doc enumerates every report
    path so frontend/codegen tooling can discover them."""
    resp = _client().get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    expected = {
        "/reports/sales-by-company",
        "/reports/sales-by-service",
        "/reports/by-destination-country",
        "/reports/top-recipients",
        "/reports/top-customers",
        "/reports/sales-by-employee",
        "/reports/cashier-productivity",
    }
    assert expected.issubset(paths)
