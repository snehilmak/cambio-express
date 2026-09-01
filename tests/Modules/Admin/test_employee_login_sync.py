"""Editing a linked employee's email/phone moves their LOGIN too.

Email and phone are the login identifier (L-2), and they were
stored on both the HR row and the auth row. Editing them on
Employees → Profile updated the HR record and left the login
alone, so the person went on signing in with the old address and
nothing anywhere said so.

The tests below are the bug (an admin corrects an email, the
person can sign in with the new one) plus the ways a naive fix
would go wrong: a collision, a clear-both lockout, and a partial
write that updates one row and not the other.
"""
import pytest

from api.Modules.Tenancy.Models import StoreEmployee, User
from tests._app import db, db_session
from tests.conftest import login_admin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, store_id):
    return _headers(login_admin(client, store_id))


def _linked(store_id, *, name, email, phone=""):
    """An employee with a login attached — the case that had the
    bug. Returns (employee_id, user_id)."""
    from api.Modules.Admin.Services.users import create_store_user

    with db_session():
        user = create_store_user(
            db.session, store_id=store_id, email=email, phone=phone,
            password="x", full_name=name, role="employee",
        )
        db.session.flush()
        emp = StoreEmployee(
            store_id=store_id, name=name, user_id=user.id,
            email=email, phone=phone,
        )
        db.session.add(emp)
        db.session.commit()
        return emp.id, user.id


def _patch(client, store_id, emp_id, body):
    return client.patch(
        f"/api/v2/admin/employees/{emp_id}",
        headers=_admin(client, store_id), json=body,
    )


# ── The bug ─────────────────────────────────────────────────


def test_changing_the_email_moves_the_login(client, test_store_id):
    """The whole point: correct someone's email on the HR tab and
    they can actually sign in with it."""
    emp_id, uid = _linked(
        test_store_id, name="Amber", email="old@shop.com",
    )
    with db_session():
        assert db.session.get(User, uid).username == "old@shop.com"

    resp = _patch(client, test_store_id, emp_id, {"email": "new@shop.com"})
    assert resp.status_code == 200, resp.text

    with db_session():
        user = db.session.get(User, uid)
        emp = db.session.get(StoreEmployee, emp_id)
        assert user.username == "new@shop.com", (
            "the login identifier must follow the HR edit"
        )
        assert user.email == "new@shop.com"
        assert emp.email == "new@shop.com"


def test_changing_the_phone_moves_the_login(client, test_store_id):
    emp_id, uid = _linked(
        test_store_id, name="Ben", email="", phone="555-0100",
    )
    resp = _patch(client, test_store_id, emp_id, {"phone": "555-0199"})
    assert resp.status_code == 200, resp.text

    with db_session():
        user = db.session.get(User, uid)
        assert "5550199" in (user.login_phone or "").replace("-", "")
        assert user.username != "5550100"


def test_the_person_can_actually_sign_in_with_the_new_email(
    client, test_store_id,
):
    """End to end — the assertion that would have caught this."""
    emp_id, _ = _linked(
        test_store_id, name="Cara", email="cara.old@shop.com",
    )
    _patch(client, test_store_id, emp_id, {"email": "cara.new@shop.com"})

    ok = client.post("/api/v2/auth/login", json={
        "username": "cara.new@shop.com", "password": "x",
        "store_id": test_store_id,
    })
    assert ok.status_code == 200, ok.text

    stale = client.post("/api/v2/auth/login", json={
        "username": "cara.old@shop.com", "password": "x",
        "store_id": test_store_id,
    })
    assert stale.status_code != 200, (
        "the old identifier must stop working"
    )


# ── Ways a naive fix breaks ─────────────────────────────────


def test_a_collision_is_refused_and_writes_nothing(
    client, test_store_id,
):
    """Two people cannot share a login identifier, and the refusal
    must leave BOTH rows untouched — a half-applied identity change
    is worse than a rejected one."""
    _linked(test_store_id, name="Amber", email="taken@shop.com")
    emp_id, uid = _linked(test_store_id, name="Ben", email="ben@shop.com")

    resp = _patch(client, test_store_id, emp_id, {"email": "taken@shop.com"})
    assert resp.status_code == 422
    assert "already signs in" in resp.text

    with db_session():
        assert db.session.get(User, uid).username == "ben@shop.com"
        assert db.session.get(StoreEmployee, emp_id).email == "ben@shop.com"


def test_clearing_both_identifiers_is_refused(client, test_store_id):
    """Blanking email and phone on a linked person would lock them
    out silently."""
    emp_id, uid = _linked(
        test_store_id, name="Amber", email="amber@shop.com",
    )
    resp = _patch(
        client, test_store_id, emp_id, {"email": "", "phone": ""},
    )
    assert resp.status_code == 422
    assert "lock them out" in resp.text
    with db_session():
        assert db.session.get(User, uid).username == "amber@shop.com"


def test_an_invalid_email_is_refused(client, test_store_id):
    emp_id, uid = _linked(
        test_store_id, name="Amber", email="amber@shop.com",
    )
    resp = _patch(client, test_store_id, emp_id, {"email": "not-an-email"})
    assert resp.status_code == 422
    with db_session():
        assert db.session.get(User, uid).username == "amber@shop.com"


def test_editing_the_phone_does_not_wipe_the_email(
    client, test_store_id,
):
    """A PATCH that names only `phone` must leave the login's email
    where it is — the sync reads unspecified fields off the login
    rather than treating them as blank."""
    emp_id, uid = _linked(
        test_store_id, name="Amber", email="amber@shop.com",
    )
    resp = _patch(client, test_store_id, emp_id, {"phone": "555-0123"})
    assert resp.status_code == 200, resp.text
    with db_session():
        user = db.session.get(User, uid)
        assert user.email == "amber@shop.com"
        # Email still wins as the identifier.
        assert user.username == "amber@shop.com"


# ── Unlinked people are untouched ───────────────────────────


def test_an_employee_with_no_login_is_unaffected(
    client, test_store_id,
):
    """Plenty of employees never sign in; their HR email is just an
    HR field and must keep working."""
    with db_session():
        emp = StoreEmployee(
            store_id=test_store_id, name="No-login Nick",
            email="nick@shop.com",
        )
        db.session.add(emp)
        db.session.commit()
        emp_id = emp.id

    resp = _patch(client, test_store_id, emp_id, {"email": "new@shop.com"})
    assert resp.status_code == 200, resp.text
    with db_session():
        assert db.session.get(StoreEmployee, emp_id).email == "new@shop.com"


def test_the_identifier_change_is_audited(client, test_store_id):
    """This changes how a person signs in — the log has to say so,
    not just "changed: email"."""
    from api.Modules.Audit.Models import OperatorAuditLog

    emp_id, _ = _linked(
        test_store_id, name="Amber", email="old@shop.com",
    )
    _patch(client, test_store_id, emp_id, {"email": "new@shop.com"})

    with db_session():
        row = (
            db.session.query(OperatorAuditLog)
            .filter_by(store_id=test_store_id, action="update_employee")
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert "login identifier" in (row.summary or "")
        assert "old@shop.com" in row.summary
        assert "new@shop.com" in row.summary
