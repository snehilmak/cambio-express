"""Regression guard: employees can see every transfer in their store,
not just today's and not just ones they personally created.

The earlier `created_by=self AND send_date=today` clamp on the
/transfers route blocked a real customer-service workflow — when a
customer comes back a few days later to update a transfer's status,
the cashier helping them this time is often a different one from
who originally logged it. Both admins and employees need full
visibility for that to work.

Cross-store isolation is still enforced by the store_id filter, and
business-level aggregate totals are hidden separately on the
employee dashboard (my_total / my_month were removed from the
template + route context).
"""
from datetime import date, datetime, timedelta
from app import app as flask_app, db


def _logged_in_employee_client_for(store_id):
    """A client authenticated as a store employee at the given store."""
    from app import User
    c = flask_app.test_client()
    with flask_app.app_context():
        emp = User(store_id=store_id, username=f"emp{store_id}@test.com",
                   full_name="Employee", role="employee")
        emp.set_password("x")
        db.session.add(emp)
        db.session.commit()
        uid = emp.id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "employee"
        sess["store_id"] = store_id
    return c


def _seed_transfer(store_id, creator_id, send_date, sender_name="Jane"):
    from app import Transfer
    with flask_app.app_context():
        t = Transfer(
            store_id=store_id, created_by=creator_id,
            send_date=send_date, company="Intermex",
            sender_name=sender_name, send_amount=100.0, fee=2.0,
            federal_tax=1.0, commission=0.0, status="Sent",
        )
        db.session.add(t)
        db.session.commit()
        return t.id


def test_employee_sees_transfers_from_past_days():
    """The test-store admin seeds a transfer dated a week ago. An
    employee logging in today should still see it on /transfers."""
    from app import Store, User
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        store_id, admin_id = store.id, admin.id
    last_week = date.today() - timedelta(days=7)
    tid = _seed_transfer(store_id, admin_id, last_week, sender_name="OldCustomer")
    c = _logged_in_employee_client_for(store_id)
    resp = c.get("/transfers")
    assert resp.status_code == 200
    assert b"OldCustomer" in resp.data


def test_employee_sees_transfers_created_by_others():
    """A transfer created by the admin (different user id) is still
    visible to an employee — anyone at the store can pick up anyone
    else's transfer to update its status."""
    from app import Store, User
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        store_id, admin_id = store.id, admin.id
    today = date.today()
    _seed_transfer(store_id, admin_id, today, sender_name="AdminLogged")
    c = _logged_in_employee_client_for(store_id)
    resp = c.get("/transfers")
    assert resp.status_code == 200
    assert b"AdminLogged" in resp.data


def test_employee_cannot_see_other_stores_transfers():
    """Cross-store isolation still holds — an employee at Store A does
    NOT see transfers from Store B."""
    from app import Store, User
    # Set up a second store with its own transfer.
    with flask_app.app_context():
        other = Store(name="Other Shop", slug="other-shop",
                      email="o@s.com", plan="trial",
                      trial_ends_at=datetime.utcnow() + timedelta(days=7))
        db.session.add(other)
        db.session.flush()
        other_admin = User(store_id=other.id, username="other@s.com",
                           full_name="Other", role="admin")
        other_admin.set_password("x")
        db.session.add(other_admin)
        db.session.commit()
        other_id, other_admin_id = other.id, other_admin.id
        store = Store.query.filter_by(slug="test-store").first()
        store_id = store.id
    today = date.today()
    _seed_transfer(other_id, other_admin_id, today, sender_name="OtherStoreOnly")
    # Sign in as an employee of the TEST store.
    c = _logged_in_employee_client_for(store_id)
    resp = c.get("/transfers")
    assert resp.status_code == 200
    assert b"OtherStoreOnly" not in resp.data


def test_employee_can_filter_by_date_range():
    """Date filters were hidden from employees when they were locked to
    today; now they're available so cashiers can narrow a historical
    search."""
    c = _logged_in_employee_client_for(_test_store_id())
    resp = c.get("/transfers")
    assert resp.status_code == 200
    # The filter inputs are rendered regardless of role.
    assert b'name="date_from"' in resp.data
    assert b'name="date_to"' in resp.data


def _test_store_id():
    from app import Store
    with flask_app.app_context():
        return Store.query.filter_by(slug="test-store").first().id
