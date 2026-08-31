"""Unified Employees hub (E-1) — the person-centric merge of the
old Cashiers roster + Team Users tabs.

Invariants under test:
  * the listing unions HR records (with linked login info) and
    login-only accounts, so no person is invisible,
  * links are 1:1, same-store, store-roles-only — violations are
    opaque 422s,
  * HR fields PATCH with clear-flags for the nullable dates and
    validate payroll_schedule,
  * everything is permission-gated on users.* and audited.
"""
from tests._app import db, db_session
from tests.conftest import login_admin, login_employee


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _mk_user(store_id, username, role="employee",
             full_name="", password="emppass1234"):
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=store_id, username=username, role=role,
            full_name=full_name, is_active=True,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


def test_create_list_and_login_only(client, test_store_id):
    token = login_admin(client, test_store_id)
    uid = _mk_user(test_store_id, "e1_hub_login", full_name="Amber R.")

    made = client.post(
        "/api/v2/admin/employees", headers=_headers(token),
        json={
            "name": "Amber R.",
            "hourly_rate": 14.5,
            "hired_on": "2026-03-02",
            "email": "amber@example.com",
            "phone": "512 555 0100",
            "payroll_schedule": "weekly",
            "user_id": uid,
        },
    )
    assert made.status_code == 201, made.get_data(as_text=True)
    row = made.get_json()
    assert row["name"] == "Amber R."
    assert row["hired_on"] == "2026-03-02"
    assert row["payroll_schedule"] == "weekly"
    assert row["login"]["user_id"] == uid
    assert row["login"]["role"] == "employee"

    # A second login with no HR record shows up as login-only.
    lonely = _mk_user(test_store_id, "e1_hub_lonely")
    listing = client.get(
        "/api/v2/admin/employees", headers=_headers(token),
    ).get_json()
    by_name = {r["name"]: r for r in listing["rows"]}
    assert by_name["Amber R."]["login"]["username"] == "e1_hub_login"
    assert lonely in [r["user_id"] for r in listing["login_only"]]
    # The linked login is NOT also listed as login-only.
    assert uid not in [r["user_id"] for r in listing["login_only"]]


def test_hr_patch_and_clear_flags(client, test_store_id):
    token = login_admin(client, test_store_id)
    made = client.post(
        "/api/v2/admin/employees", headers=_headers(token),
        json={"name": "E1 Patch", "hired_on": "2026-01-15"},
    )
    emp_id = made.get_json()["id"]

    patched = client.patch(
        f"/api/v2/admin/employees/{emp_id}", headers=_headers(token),
        json={
            "hourly_rate": 12.25,
            "date_of_birth": "2003-09-24",
            "address_line1": "1 Main St",
        },
    )
    assert patched.status_code == 200, patched.get_data(as_text=True)
    row = patched.get_json()
    assert row["hourly_rate"] == 12.25
    assert row["date_of_birth"] == "2003-09-24"
    assert row["hired_on"] == "2026-01-15"

    cleared = client.patch(
        f"/api/v2/admin/employees/{emp_id}", headers=_headers(token),
        json={"clear_hired_on": True, "clear_date_of_birth": True},
    ).get_json()
    assert cleared["hired_on"] is None
    assert cleared["date_of_birth"] is None

    bad = client.patch(
        f"/api/v2/admin/employees/{emp_id}", headers=_headers(token),
        json={"payroll_schedule": "fortnightly"},
    )
    assert bad.status_code == 422

    missing = client.patch(
        "/api/v2/admin/employees/999999", headers=_headers(token),
        json={"name": "X"},
    )
    assert missing.status_code == 404


def test_link_guards_and_unlink(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    token = login_admin(client, test_store_id)
    made = client.post(
        "/api/v2/admin/employees", headers=_headers(token),
        json={"name": "E1 Linkee"},
    )
    emp_id = made.get_json()["id"]
    made2 = client.post(
        "/api/v2/admin/employees", headers=_headers(token),
        json={"name": "E1 Rival"},
    )
    rival_id = made2.get_json()["id"]

    uid = _mk_user(test_store_id, "e1_link_target")
    linked = client.post(
        f"/api/v2/admin/employees/{emp_id}/link",
        headers=_headers(token), json={"user_id": uid},
    )
    assert linked.status_code == 200, linked.get_data(as_text=True)
    assert linked.get_json()["login"]["user_id"] == uid

    # 1:1 — the same login can't attach to a second person.
    stolen = client.post(
        f"/api/v2/admin/employees/{rival_id}/link",
        headers=_headers(token), json={"user_id": uid},
    )
    assert stolen.status_code == 422

    # Cross-store logins are opaque 422s.
    with db_session():
        other = Store(name="E1 Other", slug="e1-other", is_active=True)
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    foreign = _mk_user(other_id, "e1_foreign_login")
    denied = client.post(
        f"/api/v2/admin/employees/{rival_id}/link",
        headers=_headers(token), json={"user_id": foreign},
    )
    assert denied.status_code == 422

    # Owner-role logins have no per-store HR record.
    from api.Modules.Tenancy.Models import User
    with db_session():
        owner = User(
            store_id=test_store_id, username="e1_owner_login",
            role="owner", is_active=True,
        )
        owner.set_password("ownerpass123")
        db.session.add(owner)
        db.session.commit()
        owner_id = owner.id
    refused = client.post(
        f"/api/v2/admin/employees/{rival_id}/link",
        headers=_headers(token), json={"user_id": owner_id},
    )
    assert refused.status_code == 422

    # Unlink restores login-only visibility; User row untouched.
    undone = client.delete(
        f"/api/v2/admin/employees/{emp_id}/link",
        headers=_headers(token),
    )
    assert undone.status_code == 200
    assert undone.get_json()["login"] is None
    listing = client.get(
        "/api/v2/admin/employees", headers=_headers(token),
    ).get_json()
    assert uid in [r["user_id"] for r in listing["login_only"]]


def test_permission_gates_and_audit(client, test_store_id):
    from api.Modules.Audit.Models import OperatorAuditLog

    token = login_admin(client, test_store_id)
    made = client.post(
        "/api/v2/admin/employees", headers=_headers(token),
        json={"name": "E1 Audited"},
    )
    assert made.status_code == 201
    emp_id = made.get_json()["id"]
    with db_session():
        assert (
            db.session.query(OperatorAuditLog)
            .filter_by(
                store_id=test_store_id, action="create_employee",
                target_id=str(emp_id),
            ).first()
        ) is not None

    # Cashiers (no users.*) can't reach the hub.
    _mk_user(test_store_id, "e1_cashier_gate")
    emp_token = login_employee(
        client, test_store_id, "e1_cashier_gate",
        password="emppass1234",
    )
    assert client.get(
        "/api/v2/admin/employees", headers=_headers(emp_token),
    ).status_code == 403
    assert client.post(
        "/api/v2/admin/employees", headers=_headers(emp_token),
        json={"name": "nope"},
    ).status_code == 403
