"""Customers batch reports — Top Senders, Top Recipients, By
Destination Country, New vs. Returning Senders."""
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


def _make_customer(client, store_id, *, full_name, phone="5551234"):
    from app import Customer, db
    with client.application.app_context():
        c = Customer(store_id=store_id, full_name=full_name,
                     phone_country="+1", phone_number=phone)
        db.session.add(c); db.session.commit()
        return c.id


def _make_transfer(client, store_id, *, send_date, amount, fee=2.0,
                   federal_tax=0.0, country="MX",
                   customer_id=None, recipient_name="R",
                   confirm="X", status="Sent"):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name="S", recipient_name=recipient_name,
            country=country, confirm_number=confirm,
            company="Intermex", send_amount=amount,
            fee=fee, federal_tax=federal_tax, status=status,
            customer_id=customer_id,
        )
        db.session.add(t); db.session.commit()
        return t.id


# ── Top Senders (by transaction count) ───────────────────────




def test_top_senders_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    cid = _make_customer(client, test_store_id, full_name="Sender Joe",
                         phone="5550111")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   customer_id=cid, confirm="J1")
    resp = client.get("/reports/top-senders.csv")
    body = resp.get_data(as_text=True)
    assert "Sender Joe,+15550111,1,100.00" in body


# ── Top Recipients ───────────────────────────────────────────




def test_top_recipients_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=150,
                   recipient_name="Alice Doe", confirm="A1")
    resp = client.get("/reports/top-recipients.csv")
    body = resp.get_data(as_text=True)
    assert "Recipient,Count,Total Sent" in body
    assert "Alice Doe,1,150.00" in body


# ── By Destination Country ───────────────────────────────────


def test_by_destination_country_groups_per_country(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   country="MX", confirm="X1")
    _make_transfer(client, test_store_id, send_date=today, amount=200,
                   country="MX", confirm="X2")
    _make_transfer(client, test_store_id, send_date=today, amount=400,
                   country="GT", confirm="G1")
    resp = client.get("/reports/by-destination-country")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "MX" in body
    assert "GT" in body
    assert "$700.00" in body  # Total Sent KPI
    # GT is bigger so renders first.
    assert body.index("GT") < body.index("MX")
    assert "2 countries" in body


def test_by_destination_country_csv_has_total_row(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   country="MX", confirm="X1")
    resp = client.get("/reports/by-destination-country.csv")
    body = resp.get_data(as_text=True)
    assert "Country,Count,Total Sent" in body
    assert "MX,1,100.00" in body
    assert "TOTAL,1,100.00" in body


# ── New vs. Returning Senders ────────────────────────────────


def test_new_vs_returning_classifies_correctly(client, test_store_id):
    """Customer with a transfer BEFORE the period = returning. Customer
    whose first-ever transfer falls IN the period = new. Walk-in
    transfers (no customer_id) bucketed separately."""
    _admin_login(client, test_store_id)
    veteran = _make_customer(client, test_store_id,
                              full_name="Veteran", phone="5550101")
    rookie  = _make_customer(client, test_store_id,
                              full_name="Rookie",  phone="5550102")
    # veteran: one transfer before window, one in window.
    _make_transfer(client, test_store_id, send_date=date(2026, 4, 10),
                   amount=300, customer_id=veteran, confirm="V0")
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 2),
                   amount=200, customer_id=veteran, confirm="V1")
    # rookie: only in-window.
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 1),
                   amount=100, customer_id=rookie, confirm="R1")
    # walk-in.
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 3),
                   amount=50, customer_id=None, confirm="W1")
    resp = client.get("/reports/new-vs-returning?from=2026-05-01&to=2026-05-31")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Body labels.
    assert "New senders" in body
    assert "Returning senders" in body
    assert "Walk-in (unidentified)" in body
    # KPI counts: new=1, returning=1.
    # Total sent 200+100+50 = 350.
    assert "$350.00" in body


def test_new_vs_returning_no_walkin_bucket_when_empty(client, test_store_id):
    _admin_login(client, test_store_id)
    cid = _make_customer(client, test_store_id, full_name="Solo",
                         phone="5550999")
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 1),
                   amount=10, customer_id=cid, confirm="S1")
    resp = client.get("/reports/new-vs-returning?from=2026-05-01&to=2026-05-31")
    body = resp.get_data(as_text=True)
    # No walk-in transfers in this scenario → no bucket.
    assert "Walk-in (unidentified)" not in body


def test_new_vs_returning_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    cid = _make_customer(client, test_store_id, full_name="C", phone="5557777")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=42,
                   customer_id=cid, confirm="T1")
    resp = client.get("/reports/new-vs-returning.csv")
    body = resp.get_data(as_text=True)
    assert "Bucket,Customers,Transfers,Total Sent" in body
    assert "TOTAL," in body


# ── Auth ─────────────────────────────────────────────────────


def test_customer_batch_routes_require_admin(client):
    for path in ("/reports/top-senders",
                 "/reports/top-recipients",
                 "/reports/by-destination-country",
                 "/reports/new-vs-returning"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path
        assert "/login" in resp.headers.get("Location", ""), path
