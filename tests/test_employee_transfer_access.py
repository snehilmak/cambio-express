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
from .conftest import make_employee_client, seed_transfer


def test_employee_sees_transfers_from_past_days(test_store_id, test_admin_id):
    last_week = date.today() - timedelta(days=7)
    seed_transfer(test_store_id, test_admin_id,
                  send_date=last_week, sender_name="OldCustomer")
    c = make_employee_client(test_store_id)
    resp = c.get("/transfers")
    assert resp.status_code == 200
    assert b"OldCustomer" in resp.data


def test_employee_sees_transfers_created_by_others(test_store_id, test_admin_id):
    """A transfer created by the admin is still visible to an employee —
    anyone at the store can pick up anyone else's transfer to update
    its status."""
    seed_transfer(test_store_id, test_admin_id, sender_name="AdminLogged")
    c = make_employee_client(test_store_id)
    resp = c.get("/transfers")
    assert resp.status_code == 200
    assert b"AdminLogged" in resp.data


def test_employee_cannot_see_other_stores_transfers(test_store_id):
    """Cross-store isolation still holds — an employee at Store A does
    NOT see transfers from Store B."""
    from app import Store, User
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
    seed_transfer(other_id, other_admin_id, sender_name="OtherStoreOnly")
    # Sign in as an employee of the TEST store.
    c = make_employee_client(test_store_id)
    resp = c.get("/transfers")
    assert resp.status_code == 200
    assert b"OtherStoreOnly" not in resp.data


def test_employee_can_filter_by_date_range(test_store_id):
    """Date filters were hidden from employees when they were locked to
    today; now they're available so cashiers can narrow a historical
    search."""
    c = make_employee_client(test_store_id)
    resp = c.get("/transfers")
    assert resp.status_code == 200
    assert b'name="date_from"' in resp.data
    assert b'name="date_to"' in resp.data
