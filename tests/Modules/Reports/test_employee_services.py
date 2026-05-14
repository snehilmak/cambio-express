"""Unit tests for Reports.Services.employees — sales_by_employee,
cashier_productivity. Mirrors test_sales_services.py — same
strangler-fig equivalence checks."""
from datetime import date


def _seed_user(store_id, *, username, full_name=""):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    u = User(
        store_id=store_id, username=username,
        full_name=full_name, role="employee",
    )
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u.id


def _seed_storeemployee(store_id, *, name, is_active=True):
    from api.Modules.Tenancy.Models import StoreEmployee
    from tests._app import db
    e = StoreEmployee(store_id=store_id, name=name, is_active=is_active)
    db.session.add(e); db.session.commit()
    return e.id


def _seed_transfer(store_id, *, created_by=None, employee_id=None,
                    send_amount=100.0, status="Sent"):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
    t = Transfer(
        store_id=store_id, send_date=date.today(),
        company="Intermex", sender_name="S", recipient_name="R",
        country="MX", confirm_number=f"X{send_amount}",
        send_amount=send_amount, fee=2.0, federal_tax=1.0,
        status=status, created_by=created_by, employee_id=employee_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def test_sales_by_employee_resolves_user_names(test_store_id):
    from tests._app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        uid = _seed_user(test_store_id, username="cash@x.com",
                          full_name="Cash Cashier")
        _seed_transfer(test_store_id, created_by=uid, send_amount=300.0)
        _seed_transfer(test_store_id, created_by=uid, send_amount=200.0)

        from api.Modules.Reports.Services import sales_by_employee
        rows, totals = sales_by_employee(
            db.session, [test_store_id], today, today,
        )
    assert len(rows) == 1
    assert rows[0]["employee"] == "Cash Cashier"
    assert rows[0]["username"] == "cash@x.com"
    assert rows[0]["count"] == 2
    assert totals["sent"] == 500.0


def test_sales_by_employee_buckets_unattributed(test_store_id):
    """`Transfer.created_by IS NULL` → `(unattributed)` so legacy
    rows don't disappear from totals."""
    from tests._app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, created_by=None, send_amount=100.0)

        from api.Modules.Reports.Services import sales_by_employee
        rows, _ = sales_by_employee(db.session, [test_store_id], today, today)
    assert rows[0]["employee"] == "(unattributed)"
    assert rows[0]["username"] == ""


def test_cashier_productivity_sorts_by_count_desc(test_store_id):
    """Busiest cashier first — matches the operator's mental model."""
    from tests._app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        big = _seed_storeemployee(test_store_id, name="Maria")
        small = _seed_storeemployee(test_store_id, name="Carlos")
        # Maria handled 3, Carlos 1.
        for _ in range(3):
            _seed_transfer(test_store_id, employee_id=big, send_amount=50.0)
        _seed_transfer(test_store_id, employee_id=small, send_amount=999.0)

        from api.Modules.Reports.Services import cashier_productivity
        rows, _ = cashier_productivity(
            db.session, [test_store_id], today, today,
        )
    assert rows[0]["cashier"] == "Maria"
    assert rows[0]["count"] == 3
    assert rows[1]["cashier"] == "Carlos"


def test_cashier_productivity_marks_inactive(test_store_id):
    from tests._app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        eid = _seed_storeemployee(
            test_store_id, name="Quit", is_active=False,
        )
        _seed_transfer(test_store_id, employee_id=eid, send_amount=100.0)

        from api.Modules.Reports.Services import cashier_productivity
        rows, _ = cashier_productivity(
            db.session, [test_store_id], today, today,
        )
    assert rows[0]["is_active"] is False


# ── Customer service ────────────────────────────────────────


def test_top_customers_resolves_phones_and_walkins(test_store_id):
    from api.Modules.Customers.Models import Customer
    from api.Modules.Transfers.Models import Transfer
    from tests._app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        c = Customer(
            store_id=test_store_id, full_name="Alice",
            phone_country="+1", phone_number="5551234",
        )
        db.session.add(c); db.session.commit()
        # One linked transfer + one walk-in.
        t1 = Transfer(
            store_id=test_store_id, send_date=today,
            company="Intermex", sender_name="Alice",
            recipient_name="R", country="MX", confirm_number="X1",
            send_amount=100.0, fee=2.0, federal_tax=1.0,
            status="Sent", customer_id=c.id,
        )
        t2 = Transfer(
            store_id=test_store_id, send_date=today,
            company="Intermex", sender_name="Walk",
            recipient_name="R", country="MX", confirm_number="X2",
            send_amount=50.0, fee=1.0, federal_tax=0.5,
            status="Sent", customer_id=None,
        )
        db.session.add_all([t1, t2]); db.session.commit()

        from api.Modules.Reports.Services import top_customers
        rows, _ = top_customers(db.session, [test_store_id], today, today)

    by_label = {r["customer"]: r for r in rows}
    assert "Alice" in by_label
    assert by_label["Alice"]["phone"] == "+15551234"
    assert "(walk-in)" in by_label
    assert by_label["(walk-in)"]["phone"] == ""
