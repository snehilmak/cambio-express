"""Sales batch reports — Service Type, Employee, Top Customers.

Each follows the same pattern as Sales by Company (#170): aggregate
Transfer rows in a date range, exclude Canceled / Rejected, expose
KPIs + per-row metrics, plus a CSV variant of the same query.
"""
from datetime import date


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
                   service_type="Money Transfer",
                   created_by=None, customer_id=None,
                   sender_name="S", confirm="X", status="Sent"):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name=sender_name, recipient_name="R",
            country="MX", confirm_number=confirm,
            company=company, service_type=service_type,
            send_amount=amount, fee=fee, federal_tax=federal_tax,
            status=status,
            created_by=created_by, customer_id=customer_id,
        )
        db.session.add(t); db.session.commit()
        return t.id


def _make_employee(client, store_id, *, username, full_name=""):
    from app import User, db
    with client.application.app_context():
        u = User(username=username, full_name=full_name,
                 role="employee", store_id=store_id)
        u.set_password("p")
        db.session.add(u); db.session.commit()
        return u.id


def _make_customer(client, store_id, *, full_name, phone="5551234"):
    from app import Customer, db
    with client.application.app_context():
        c = Customer(store_id=store_id, full_name=full_name,
                     phone_country="+1", phone_number=phone)
        db.session.add(c); db.session.commit()
        return c.id


# ── Sales by Service Type ────────────────────────────────────


def test_sales_by_service_type_groups_per_service(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today,
                   amount=200, fee=2.0,
                   service_type="Money Transfer", confirm="MT1")
    _make_transfer(client, test_store_id, send_date=today,
                   amount=100, fee=1.5,
                   service_type="Bill Payment", confirm="BP1")
    _make_transfer(client, test_store_id, send_date=today,
                   amount=50, fee=0.5,
                   service_type="Top Up", confirm="TU1")
    resp = client.get("/reports/sales-by-service-type")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Sales by Service Type" in body
    assert "Money Transfer" in body
    assert "Bill Payment" in body
    assert "Top Up" in body
    assert "$350.00" in body  # Total Sent KPI
    assert "3 service types" in body


def test_sales_by_service_type_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today,
                   amount=100, service_type="Money Transfer", confirm="A")
    resp = client.get("/reports/sales-by-service-type.csv")
    assert resp.mimetype == "text/csv"
    body = resp.get_data(as_text=True)
    assert "Service Type,Count,Total Sent,Total Fees,Federal Tax,Avg Transfer" in body
    assert "Money Transfer,1,100.00" in body
    assert "TOTAL,1,100.00" in body


# ── Sales by Employee ────────────────────────────────────────


def test_sales_by_employee_resolves_user_names(client, test_store_id):
    _admin_login(client, test_store_id)
    alice = _make_employee(client, test_store_id, username="alice",
                           full_name="Alice Cashier")
    bob = _make_employee(client, test_store_id, username="bob",
                         full_name="Bob Cashier")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=300,
                   created_by=alice, confirm="A1")
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   created_by=bob, confirm="B1")
    # Legacy unattributed transfer.
    _make_transfer(client, test_store_id, send_date=today, amount=50,
                   created_by=None, confirm="L1")
    resp = client.get("/reports/sales-by-employee")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Alice Cashier" in body
    assert "Bob Cashier" in body
    assert "(unattributed)" in body
    assert "$450.00" in body  # Total Sent KPI


def test_sales_by_employee_falls_back_to_username_when_no_full_name(
        client, test_store_id):
    _admin_login(client, test_store_id)
    only_uname = _make_employee(client, test_store_id, username="charlie",
                                 full_name="")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   created_by=only_uname, confirm="C1")
    resp = client.get("/reports/sales-by-employee")
    body = resp.get_data(as_text=True)
    assert "charlie" in body


def test_sales_by_employee_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    e = _make_employee(client, test_store_id, username="dee",
                       full_name="Dee Cashier")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=200,
                   created_by=e, confirm="D1")
    resp = client.get("/reports/sales-by-employee.csv")
    assert resp.mimetype == "text/csv"
    body = resp.get_data(as_text=True)
    assert "Employee,Username,Count,Total Sent" in body
    assert "Dee Cashier,dee,1,200.00" in body


# ── Top Customers by Volume ──────────────────────────────────


def test_top_customers_resolves_customer_rows(client, test_store_id):
    _admin_login(client, test_store_id)
    big = _make_customer(client, test_store_id, full_name="Big Sender",
                         phone="5550001")
    small = _make_customer(client, test_store_id, full_name="Small Sender",
                           phone="5550002")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=500,
                   customer_id=big, confirm="B1")
    _make_transfer(client, test_store_id, send_date=today, amount=400,
                   customer_id=big, confirm="B2")
    _make_transfer(client, test_store_id, send_date=today, amount=50,
                   customer_id=small, confirm="S1")
    resp = client.get("/reports/top-customers")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Customer names + phone appear.
    assert "Big Sender" in body
    assert "Small Sender" in body
    assert "+15550001" in body
    # KPIs.
    assert "$950.00" in body
    assert "2 customers" in body
    # Top customer (sorted desc by sent) appears before the smaller.
    assert body.index("Big Sender") < body.index("Small Sender")


def test_top_customers_buckets_walkin_transfers(client, test_store_id):
    """Transfers without a customer_id go into a single (walk-in) row,
    so totals match the dashboard."""
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=80,
                   customer_id=None, sender_name="Walk", confirm="W1")
    _make_transfer(client, test_store_id, send_date=today, amount=20,
                   customer_id=None, sender_name="Walk2", confirm="W2")
    resp = client.get("/reports/top-customers")
    body = resp.get_data(as_text=True)
    assert "(walk-in)" in body
    assert "$100.00" in body  # Total Sent KPI


def test_top_customers_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    cid = _make_customer(client, test_store_id, full_name="CSV Sender",
                         phone="5550999")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=300,
                   customer_id=cid, confirm="X1")
    resp = client.get("/reports/top-customers.csv")
    assert resp.mimetype == "text/csv"
    body = resp.get_data(as_text=True)
    assert "Customer,Phone,Count,Total Sent" in body
    assert "CSV Sender,+15550999,1,300.00" in body


# ── Auth ─────────────────────────────────────────────────────


def test_sales_batch_routes_require_admin(client):
    for path in ("/reports/sales-by-service-type",
                 "/reports/sales-by-employee",
                 "/reports/top-customers"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path
        assert "/login" in resp.headers.get("Location", ""), path
