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
