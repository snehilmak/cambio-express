"""Tests for the new Service Type field on Transfers.

Money Transfer (the historical default) keeps the store's federal tax
rate. Bill Payment, Top Up, and Recharge are all non-remittance flows
that the cashier may run through the same companies but they don't
carry the federal tax — server-side this is _federal_tax_for() in
app.py.
"""
from datetime import date
from app import app as flask_app, db


def _seed_admin_session():
    """Use the same admin@test.com session as logged_in_client, but
    return ids so we can assert on the stored Transfer row."""
    from app import Store, User
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        return store.id, admin.id


def _new_transfer_payload(send_amount=500.0, service_type="Money Transfer"):
    """Minimum valid payload for POST /transfers/new."""
    return {
        "send_date": date.today().isoformat(),
        "company": "Intermex",
        "service_type": service_type,
        "sender_name": "Jane Doe",
        "send_amount": str(send_amount),
        "fee": "5",
        "commission": "0",
        "recipient_name": "John",
        "country": "Mexico",
        "status": "Sent",
        "employee_id": "",  # filled below
    }


def _ensure_employee(store_id):
    from app import StoreEmployee
    with flask_app.app_context():
        e = StoreEmployee(store_id=store_id, name="Maria", is_active=True)
        db.session.add(e)
        db.session.commit()
        return e.id


# ── Tax-exempt service types zero out federal_tax ──────────────

def test_money_transfer_applies_federal_tax(logged_in_client):
    """Default service: store rate × send_amount."""
    from app import Transfer
    store_id, _ = _seed_admin_session()
    emp_id = _ensure_employee(store_id)
    payload = _new_transfer_payload(send_amount=500.0, service_type="Money Transfer")
    payload["employee_id"] = str(emp_id)
    resp = logged_in_client.post("/transfers/new", data=payload, follow_redirects=False)
    assert resp.status_code == 302
    with flask_app.app_context():
        t = Transfer.query.filter_by(sender_name="Jane Doe").first()
        assert t is not None
        assert t.service_type == "Money Transfer"
        # Test conftest seeds Store.federal_tax_rate at default 0.01 (1%).
        assert abs(t.federal_tax - 5.00) < 0.01


def test_bill_payment_skips_federal_tax(logged_in_client):
    """Bill Payment is exempt — federal_tax must be 0 even though the
    store has a non-zero rate configured."""
    from app import Transfer
    store_id, _ = _seed_admin_session()
    emp_id = _ensure_employee(store_id)
    payload = _new_transfer_payload(send_amount=500.0, service_type="Bill Payment")
    payload["employee_id"] = str(emp_id)
    resp = logged_in_client.post("/transfers/new", data=payload, follow_redirects=False)
    assert resp.status_code == 302
    with flask_app.app_context():
        t = Transfer.query.filter_by(sender_name="Jane Doe").first()
        assert t is not None
        assert t.service_type == "Bill Payment"
        assert t.federal_tax == 0.0


def test_top_up_skips_federal_tax(logged_in_client):
    from app import Transfer
    store_id, _ = _seed_admin_session()
    emp_id = _ensure_employee(store_id)
    payload = _new_transfer_payload(send_amount=300.0, service_type="Top Up")
    payload["employee_id"] = str(emp_id)
    logged_in_client.post("/transfers/new", data=payload)
    with flask_app.app_context():
        t = Transfer.query.filter_by(sender_name="Jane Doe").first()
        assert t.service_type == "Top Up"
        assert t.federal_tax == 0.0


def test_recharge_skips_federal_tax(logged_in_client):
    from app import Transfer
    store_id, _ = _seed_admin_session()
    emp_id = _ensure_employee(store_id)
    payload = _new_transfer_payload(send_amount=200.0, service_type="Recharge")
    payload["employee_id"] = str(emp_id)
    logged_in_client.post("/transfers/new", data=payload)
    with flask_app.app_context():
        t = Transfer.query.filter_by(sender_name="Jane Doe").first()
        assert t.service_type == "Recharge"
        assert t.federal_tax == 0.0


# ── Editing the service type re-triggers the rule ──────────────

def test_editing_service_type_to_exempt_drops_tax(logged_in_client):
    """Start as a Money Transfer (taxed). Edit to Bill Payment → tax goes
    to 0 even without changing the send amount."""
    from app import Transfer
    store_id, _ = _seed_admin_session()
    emp_id = _ensure_employee(store_id)
    payload = _new_transfer_payload(send_amount=400.0, service_type="Money Transfer")
    payload["employee_id"] = str(emp_id)
    logged_in_client.post("/transfers/new", data=payload)
    with flask_app.app_context():
        t = Transfer.query.filter_by(sender_name="Jane Doe").first()
        tid = t.id
        assert t.federal_tax == 4.0   # 1% of 400
    payload["service_type"] = "Bill Payment"
    logged_in_client.post(f"/transfers/{tid}/edit", data=payload)
    with flask_app.app_context():
        t = db.session.get(Transfer, tid)
        assert t.service_type == "Bill Payment"
        assert t.federal_tax == 0.0


def test_editing_service_type_back_to_mt_restores_tax(logged_in_client):
    """And the reverse — Bill Payment → Money Transfer brings the tax
    back without re-entering the send amount."""
    from app import Transfer
    store_id, _ = _seed_admin_session()
    emp_id = _ensure_employee(store_id)
    payload = _new_transfer_payload(send_amount=600.0, service_type="Top Up")
    payload["employee_id"] = str(emp_id)
    logged_in_client.post("/transfers/new", data=payload)
    with flask_app.app_context():
        t = Transfer.query.filter_by(sender_name="Jane Doe").first()
        tid = t.id
        assert t.federal_tax == 0.0
    payload["service_type"] = "Money Transfer"
    logged_in_client.post(f"/transfers/{tid}/edit", data=payload)
    with flask_app.app_context():
        t = db.session.get(Transfer, tid)
        assert t.service_type == "Money Transfer"
        assert abs(t.federal_tax - 6.0) < 0.01   # 1% of 600


# ── Unknown / blank service type defaults to Money Transfer ────

def test_unknown_service_type_falls_back_to_money_transfer(logged_in_client):
    """A bogus client value mustn't be the path to no-tax. Coerced to
    Money Transfer and taxed normally."""
    from app import Transfer
    store_id, _ = _seed_admin_session()
    emp_id = _ensure_employee(store_id)
    payload = _new_transfer_payload(send_amount=100.0, service_type="Wire Fraud")
    payload["employee_id"] = str(emp_id)
    logged_in_client.post("/transfers/new", data=payload)
    with flask_app.app_context():
        t = Transfer.query.filter_by(sender_name="Jane Doe").first()
        assert t.service_type == "Money Transfer"
        assert abs(t.federal_tax - 1.0) < 0.01


# ── Form renders the dropdown ─────────────────────────────────

def test_new_transfer_form_renders_service_dropdown(logged_in_client):
    resp = logged_in_client.get("/transfers/new")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'name="service_type"' in html
    assert "Money Transfer" in html
    assert "Bill Payment" in html
    assert "Top Up" in html
    assert "Recharge" in html
