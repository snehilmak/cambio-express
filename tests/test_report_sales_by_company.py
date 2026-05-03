"""Sales by Company — first generated report under the Report Center.

Aggregates Transfer rows by company within a date range, exposes
KPIs + a per-company breakdown, and offers a CSV export of the
same query. These tests exercise the aggregation, the period-filter
defaults, KPI rendering, and CSV output.
"""
from datetime import date, datetime


def _admin_login(client, store_id):
    from app import User, Store, db
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


def _make_transfer(client, store_id, *, send_date, amount, fee=2.0,
                   federal_tax=0.0, company="Intermex",
                   confirm="X", status="Sent"):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name="S", recipient_name="R",
            country="MX", confirm_number=confirm,
            company=company, send_amount=amount,
            fee=fee, federal_tax=federal_tax, status=status,
        )
        db.session.add(t); db.session.commit()
        return t.id


def test_sales_by_company_aggregates_per_company(client, test_store_id):
    """Three Intermex + one Maxi → two grouped rows. Sent / fees /
    tax / count totals per company; rows sorted by Sent desc."""
    _admin_login(client, test_store_id)
    today = date.today()
    in_period = today  # default period is first-of-month → today
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=200, fee=2.0, federal_tax=2.0,
                   company="Intermex", confirm="A1")
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=300, fee=3.0, federal_tax=3.0,
                   company="Intermex", confirm="A2")
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=400, fee=4.0, federal_tax=4.0,
                   company="Intermex", confirm="A3")
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=150, fee=2.5, federal_tax=1.5,
                   company="Maxi", confirm="B1")
    resp = client.get("/reports/sales-by-company")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Page header + KPIs.
    assert "Sales by Company" in body
    assert "$1,050.00" in body  # Total Sent (200+300+400+150)
    assert "$11.50" in body     # Total Fees
    assert "$10.50" in body     # Total Federal Tax
    # Both groups present (CSS uppercases visually; markup stays mixed-case).
    assert "Intermex" in body
    assert "Maxi" in body
    # Per-group Sent totals.
    assert "$900.00" in body  # Intermex sent
    assert "$150.00" in body  # Maxi sent
    # Result count says 2 companies.
    assert "2 companies" in body
    # CSV export link.
    assert "/reports/sales-by-company.csv" in body


def test_sales_by_company_excludes_canceled_and_rejected(client, test_store_id):
    """Same convention as the dashboard / owner pages — Canceled and
    Rejected transfers don't count toward totals."""
    _admin_login(client, test_store_id)
    today = date.today()
    in_period = today  # default period is first-of-month → today
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=100, company="Intermex", confirm="OK",
                   status="Sent")
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=999, company="Intermex", confirm="CX",
                   status="Canceled")
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=555, company="Intermex", confirm="RJ",
                   status="Rejected")
    resp = client.get("/reports/sales-by-company")
    body = resp.get_data(as_text=True)
    assert "$100.00" in body
    assert "$999.00" not in body
    assert "$555.00" not in body


def test_sales_by_company_respects_period_filter(client, test_store_id):
    """Rows outside the explicit ?from / ?to range don't appear."""
    _admin_login(client, test_store_id)
    in_window  = date(2026, 5, 5)
    out_window = date(2026, 4, 28)
    _make_transfer(client, test_store_id, send_date=in_window,
                   amount=100, company="Intermex", confirm="IN")
    _make_transfer(client, test_store_id, send_date=out_window,
                   amount=999, company="Intermex", confirm="OUT")
    resp = client.get("/reports/sales-by-company?from=2026-05-01&to=2026-05-31")
    body = resp.get_data(as_text=True)
    assert "$100.00" in body
    assert "$999.00" not in body


def test_sales_by_company_default_period_is_current_month(client,
                                                            test_store_id):
    """No ?from/?to → defaults to first-of-this-month → today, so a
    transfer logged earlier this month appears."""
    _admin_login(client, test_store_id)
    today = date.today()
    early_this_month = date(today.year, today.month, 1)
    _make_transfer(client, test_store_id, send_date=early_this_month,
                   amount=42, company="Intermex", confirm="DEF")
    resp = client.get("/reports/sales-by-company")
    body = resp.get_data(as_text=True)
    assert "$42.00" in body


def test_sales_by_company_empty_state(client, test_store_id):
    """No transfers in the window → empty-state message, KPI zeros."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports/sales-by-company")
    body = resp.get_data(as_text=True)
    assert "No transfers in this period." in body
    assert "$0.00" in body  # KPI zero
    assert "0 companies" in body


def test_sales_by_company_csv_exports_per_company(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    in_period = today  # default period is first-of-month → today
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=200, fee=2.0, federal_tax=1.0,
                   company="Intermex", confirm="A1")
    _make_transfer(client, test_store_id, send_date=in_period,
                   amount=300, fee=3.0, federal_tax=1.5,
                   company="Maxi", confirm="B1")
    resp = client.get("/reports/sales-by-company.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    body = resp.get_data(as_text=True)
    assert "Company,Count,Total Sent,Total Fees,Federal Tax,Avg Transfer" in body
    assert "Intermex,1,200.00,2.00,1.00,200.00" in body
    assert "Maxi,1,300.00,3.00,1.50,300.00" in body
    assert "TOTAL,2,500.00,5.00,2.50," in body


def test_sales_by_company_requires_admin(client):
    """Anonymous user gets bounced to login."""
    resp = client.get("/reports/sales-by-company", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/login" in resp.headers.get("Location", "")
