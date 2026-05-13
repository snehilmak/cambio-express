"""Tests for the Cashier Productivity report.

Sister to Sales by Employee, but groups by `Transfer.employee_id`
(the cashier-on-duty selected via the form's "Processed by" dropdown)
rather than `created_by` (the login User who saved the row). The
distinction matters for stores where one admin logs transfers on
behalf of multiple cashiers.
"""
from datetime import date


def _admin_login(client, store_id):
    from api.Modules.Tenancy.Models import Store, User
    from app import db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def _make_employee(client, store_id, *, name, is_active=True):
    from api.Modules.Tenancy.Models import StoreEmployee
    from app import db
    with client.application.app_context():
        e = StoreEmployee(store_id=store_id, name=name, is_active=is_active)
        db.session.add(e); db.session.commit()
        return e.id


def _make_transfer(client, store_id, *, send_date, amount, fee=2.0,
                   employee_id=None, employee_name=""):
    from api.Modules.Transfers.Models import Transfer
    from app import db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name="S", recipient_name="R",
            country="MX", confirm_number="X",
            company="Intermex", send_amount=amount,
            fee=fee, federal_tax=0.0, status="Sent",
            employee_id=employee_id, employee_name=employee_name,
        )
        db.session.add(t); db.session.commit()
        return t.id


def test_cashier_productivity_groups_by_employee_id(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    maria = _make_employee(client, test_store_id, name="Maria")
    carlos = _make_employee(client, test_store_id, name="Carlos")
    # Maria handled 3 transfers totaling $1500.
    for amt in (500, 500, 500):
        _make_transfer(client, test_store_id, send_date=today,
                       amount=amt, employee_id=maria, employee_name="Maria")
    # Carlos handled 1 transfer for $200.
    _make_transfer(client, test_store_id, send_date=today,
                   amount=200, employee_id=carlos, employee_name="Carlos")

    # Direct data-fn unit test — the registry-driven route adds CSRF
    # state, period chip, etc. that the data fn doesn't care about.
    from app import db
    from api.Modules.Reports.Services import cashier_productivity
    rows, totals = cashier_productivity(
        db.session, [test_store_id], today, today,
    )

    assert totals["count"] == 4
    assert totals["sent"] == 1700.0
    # Sorted by count desc — Maria first.
    assert rows[0]["cashier"] == "Maria"
    assert rows[0]["count"] == 3
    assert rows[0]["sent"] == 1500.0
    assert rows[0]["is_active"] is True
    assert rows[1]["cashier"] == "Carlos"
    assert rows[1]["count"] == 1


def test_cashier_productivity_marks_inactive(client, test_store_id):
    """Inactive cashiers still appear so historical productivity isn't
    lost when a roster row is deactivated."""
    _admin_login(client, test_store_id)
    today = date.today()
    quit_emp = _make_employee(client, test_store_id, name="Quit",
                               is_active=False)
    _make_transfer(client, test_store_id, send_date=today,
                   amount=100, employee_id=quit_emp, employee_name="Quit")

    from app import db
    from api.Modules.Reports.Services import cashier_productivity
    rows, totals = cashier_productivity(
        db.session, [test_store_id], today, today,
    )
    assert len(rows) == 1
    assert rows[0]["cashier"] == "Quit"
    assert rows[0]["is_active"] is False




def test_cashier_productivity_listed_in_report_center(client, test_store_id):
    """The Report Center landing moved to React in PR #406. The
    invariant — Cashier Productivity appears in the per-store
    report registry and links to /reports/cashier-productivity —
    now lives on the JSON envelope the SPA fetches."""
    _admin_login(client, test_store_id)
    jwt = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": test_store_id},
    ).get_json()["access_token"]
    resp = client.get(
        "/api/v2/reports",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    rows = [r for cat in resp.get_json()["categories"] for r in cat["reports"]]
    cashier = next((r for r in rows if r["key"] == "cashier_productivity"), None)
    assert cashier is not None, "cashier_productivity missing from report center"
    assert cashier["label"] == "Cashier Productivity"
    assert cashier["url"] == "/reports/cashier-productivity"


def test_cashier_productivity_csv_export(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    maria = _make_employee(client, test_store_id, name="Maria")
    _make_transfer(client, test_store_id, send_date=today, amount=500,
                   employee_id=maria, employee_name="Maria")

    resp = client.get("/reports/cashier-productivity.csv")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/csv")
    body = resp.get_data(as_text=True)
    # Header row + Maria row + TOTAL row.
    assert "Cashier" in body
    assert "Maria" in body
    assert "TOTAL" in body
