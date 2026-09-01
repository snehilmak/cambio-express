"""Named access roles (R-3).

The feature is a convenience wrapper over a SECURITY boundary, so
the tests are mostly about the boundary, not the convenience:

* editing a role really does change what its members can do (live
  propagation — the owner's explicit choice), and revokes their
  sessions so old JWT perms die;
* editing one member by hand DETACHES them, so the next role edit
  cannot silently revert an edit someone watched succeed;
* removing a label — un-assigning or deleting the role — never
  changes anyone's access, in either direction;
* a role cannot reach across stores.
"""
import pytest

from api.Core.Permissions import check_permission, resolve_user_grants
from api.Modules.Tenancy.Models import StoreRole, User
from tests._app import db, db_session
from tests.conftest import login_admin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, store_id):
    return _headers(login_admin(client, store_id))


def _matrix(**resources) -> dict:
    """Sparse matrix helper: ``_matrix(transfers=["read"])``."""
    return {
        resource: {action: True for action in actions}
        for resource, actions in resources.items()
    }


def _mk_user(store_id, name, role="employee"):
    import os
    with db_session():
        u = User(
            store_id=store_id,
            username=f"{name}_{os.urandom(2).hex()}@test.com",
            full_name=name, role=role,
        )
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        return u.id


def _create_role(client, store_id, name, matrix):
    resp = client.post(
        "/api/v2/admin/roles",
        headers=_admin(client, store_id),
        json={"name": name, "matrix": matrix},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assign(client, store_id, user_id, role_id):
    resp = client.put(
        f"/api/v2/admin/users/{user_id}/role",
        headers=_admin(client, store_id),
        json={"role_id": role_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _grants(user_id, store_id):
    return resolve_user_grants(user_id, "employee", store_id)


# ── Creating + assigning ────────────────────────────────────


def test_create_role_and_assign_applies_access_immediately(
    client, test_store_id,
):
    """Assigning must write the overlay now, not at the user's
    second login — a new hire is restricted from the first."""
    role = _create_role(
        client, test_store_id, "Shift lead",
        _matrix(transfers=["read", "create"], time_clock=["read"]),
    )
    uid = _mk_user(test_store_id, "Amber")
    _assign(client, test_store_id, uid, role["id"])

    grants = _grants(uid, test_store_id)
    assert ("transfers", "read") in grants
    assert ("transfers", "create") in grants
    assert ("time_clock", "read") in grants
    # A resource the role does not mention is DENIED, not inherited.
    assert ("monthly", "read") not in grants
    assert check_permission(
        "employee", test_store_id, "transfers", "read", user_id=uid,
    )
    assert not check_permission(
        "employee", test_store_id, "monthly", "read", user_id=uid,
    )


def test_duplicate_role_name_is_rejected(client, test_store_id):
    _create_role(client, test_store_id, "Bookkeeper", _matrix())
    resp = client.post(
        "/api/v2/admin/roles",
        headers=_admin(client, test_store_id),
        json={"name": "Bookkeeper", "matrix": _matrix()},
    )
    assert resp.status_code == 422
    assert "already exists" in resp.text


def test_blank_name_is_rejected(client, test_store_id):
    resp = client.post(
        "/api/v2/admin/roles",
        headers=_admin(client, test_store_id),
        json={"name": "   ", "matrix": _matrix()},
    )
    assert resp.status_code == 422


# ── Live propagation — the owner's decision ─────────────────


def test_editing_a_role_changes_every_member_live(
    client, test_store_id,
):
    """The whole point of R-3: widen the role, everyone widens."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    amber = _mk_user(test_store_id, "Amber")
    ben = _mk_user(test_store_id, "Ben")
    _assign(client, test_store_id, amber, role["id"])
    _assign(client, test_store_id, ben, role["id"])

    assert ("monthly", "read") not in _grants(amber, test_store_id)

    resp = client.put(
        f"/api/v2/admin/roles/{role['id']}",
        headers=_admin(client, test_store_id),
        json={"matrix": _matrix(transfers=["read"], monthly=["read"])},
    )
    assert resp.status_code == 200, resp.text

    for uid in (amber, ben):
        assert ("monthly", "read") in _grants(uid, test_store_id), (
            "a role edit must reach every member"
        )


def test_narrowing_a_role_removes_access_from_members(
    client, test_store_id,
):
    """Propagation has to work in the direction that matters for
    security, not just the generous one."""
    role = _create_role(
        client, test_store_id, "Shift lead",
        _matrix(transfers=["read", "create", "update"]),
    )
    uid = _mk_user(test_store_id, "Amber")
    _assign(client, test_store_id, uid, role["id"])
    assert ("transfers", "update") in _grants(uid, test_store_id)

    client.put(
        f"/api/v2/admin/roles/{role['id']}",
        headers=_admin(client, test_store_id),
        json={"matrix": _matrix(transfers=["read"])},
    )
    grants = _grants(uid, test_store_id)
    assert ("transfers", "read") in grants
    assert ("transfers", "update") not in grants
    assert ("transfers", "create") not in grants


def test_edit_reports_who_it_affected(client, test_store_id):
    """The SPA names these people in the confirmation — "changes
    access for 2 people" without names is not a confirmation."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    amber = _mk_user(test_store_id, "Amber")
    ben = _mk_user(test_store_id, "Ben")
    _assign(client, test_store_id, amber, role["id"])
    _assign(client, test_store_id, ben, role["id"])

    resp = client.put(
        f"/api/v2/admin/roles/{role['id']}",
        headers=_admin(client, test_store_id),
        json={"matrix": _matrix(monthly=["read"])},
    )
    names = {m["name"] for m in resp.json()["affected_members"]}
    assert names == {"Amber", "Ben"}

    members = client.get(
        f"/api/v2/admin/roles/{role['id']}/members",
        headers=_admin(client, test_store_id),
    ).json()
    assert {m["name"] for m in members["members"]} == {"Amber", "Ben"}


def test_rename_only_touches_nobody(client, test_store_id):
    """A rename is not a permission change and must not revoke
    anyone's session or rewrite an overlay."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    uid = _mk_user(test_store_id, "Amber")
    _assign(client, test_store_id, uid, role["id"])
    before = _grants(uid, test_store_id)

    resp = client.put(
        f"/api/v2/admin/roles/{role['id']}",
        headers=_admin(client, test_store_id),
        json={"name": "Floor lead"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Floor lead"
    assert resp.json()["affected_members"] == []
    assert _grants(uid, test_store_id) == before


def test_role_edit_revokes_member_sessions(client, test_store_id):
    """Perms are baked into the JWT at login, so a propagating edit
    has to revoke the members' refresh tokens or the change waits
    until they happen to log in again."""
    from datetime import timedelta

    from api.Core.Clock import utc_now
    from api.Modules.Auth.Models import RefreshToken

    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    uid = _mk_user(test_store_id, "Amber")
    _assign(client, test_store_id, uid, role["id"])

    with db_session():
        db.session.add(RefreshToken(
            user_id=uid, jti="r3-live-token",
            expires_at=utc_now() + timedelta(days=7),
        ))
        db.session.commit()

    client.put(
        f"/api/v2/admin/roles/{role['id']}",
        headers=_admin(client, test_store_id),
        json={"matrix": _matrix(monthly=["read"])},
    )

    with db_session():
        token = (
            db.session.query(RefreshToken)
            .filter_by(jti="r3-live-token").one()
        )
        assert token.revoked_at is not None, (
            "a propagating edit must revoke each member's sessions"
        )


# ── Detach: the silent-revert trap ──────────────────────────


def test_editing_one_member_detaches_them_from_the_role(
    client, test_store_id,
):
    """Amber gets a hand tweak. She must leave the role — otherwise
    the next role edit quietly undoes an edit that appeared to
    save."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    amber = _mk_user(test_store_id, "Amber")
    ben = _mk_user(test_store_id, "Ben")
    _assign(client, test_store_id, amber, role["id"])
    _assign(client, test_store_id, ben, role["id"])

    resp = client.put(
        f"/api/v2/admin/users/{amber}/permissions",
        headers=_admin(client, test_store_id),
        json={"matrix": _matrix(transfers=["read"], reports=["read"])},
    )
    assert resp.status_code == 200, resp.text

    with db_session():
        assert db.session.get(User, amber).store_role_id is None
        assert db.session.get(User, ben).store_role_id == role["id"]

    # …and the next role edit leaves Amber's hand-set access alone.
    client.put(
        f"/api/v2/admin/roles/{role['id']}",
        headers=_admin(client, test_store_id),
        json={"matrix": _matrix(transfers=["read"], monthly=["read"])},
    )
    amber_grants = _grants(amber, test_store_id)
    assert ("reports", "read") in amber_grants, (
        "a detached member's hand-set access must survive a role edit"
    )
    assert ("monthly", "read") not in amber_grants
    assert ("monthly", "read") in _grants(ben, test_store_id)


def test_clearing_a_members_overlay_also_drops_the_label(
    client, test_store_id,
):
    """No overlay means no role — the label would be claiming an
    access set that is no longer applied."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    uid = _mk_user(test_store_id, "Amber")
    _assign(client, test_store_id, uid, role["id"])

    resp = client.delete(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_admin(client, test_store_id),
    )
    assert resp.status_code == 200, resp.text
    with db_session():
        assert db.session.get(User, uid).store_role_id is None


# ── Removing a label never changes access ───────────────────


def test_unassigning_keeps_the_users_access(client, test_store_id):
    """Taking the label off must not silently widen someone back to
    their base role."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    uid = _mk_user(test_store_id, "Amber")
    _assign(client, test_store_id, uid, role["id"])
    before = _grants(uid, test_store_id)

    _assign(client, test_store_id, uid, None)
    with db_session():
        assert db.session.get(User, uid).store_role_id is None
    assert _grants(uid, test_store_id) == before


def test_deleting_a_role_keeps_member_access(client, test_store_id):
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    uid = _mk_user(test_store_id, "Amber")
    _assign(client, test_store_id, uid, role["id"])
    before = _grants(uid, test_store_id)

    resp = client.delete(
        f"/api/v2/admin/roles/{role['id']}",
        headers=_admin(client, test_store_id),
    )
    assert resp.status_code == 200, resp.text
    assert {m["name"] for m in resp.json()["detached"]} == {"Amber"}
    assert _grants(uid, test_store_id) == before
    with db_session():
        assert db.session.get(User, uid).store_role_id is None
        assert db.session.get(StoreRole, role["id"]) is None


# ── Scoping + listing ───────────────────────────────────────


def test_roles_do_not_leak_across_stores(client, test_store_id):
    from api.Modules.Tenancy.Models import Store

    with db_session():
        other = Store(
            name="Other", slug="other-role-store",
            email="other-role@x.com", plan="basic",
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        foreign = StoreRole(store_id=other_id, name="Theirs")
        db.session.add(foreign)
        db.session.commit()
        foreign_id = foreign.id

    h = _admin(client, test_store_id)
    assert client.get(
        f"/api/v2/admin/roles/{foreign_id}/members", headers=h,
    ).status_code == 404
    assert client.put(
        f"/api/v2/admin/roles/{foreign_id}", headers=h,
        json={"name": "Mine now"},
    ).status_code == 404
    assert client.delete(
        f"/api/v2/admin/roles/{foreign_id}", headers=h,
    ).status_code == 404
    listed = client.get("/api/v2/admin/roles", headers=h).json()
    assert "Theirs" not in {r["name"] for r in listed["roles"]}


def test_list_reports_member_counts(client, test_store_id):
    """The count is what makes an edit's blast radius visible
    before you open it."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    for name in ("Amber", "Ben", "Cara"):
        _assign(
            client, test_store_id,
            _mk_user(test_store_id, name), role["id"],
        )
    listed = client.get(
        "/api/v2/admin/roles", headers=_admin(client, test_store_id),
    ).json()
    row = next(r for r in listed["roles"] if r["id"] == role["id"])
    assert row["member_count"] == 3
    assert row["matrix"]["transfers"]["read"] is True
    assert row["matrix"]["monthly"]["read"] is False


def test_cannot_assign_a_role_to_yourself(client, test_store_id):
    """Same self-edit guard the per-user overlay routes carry — an
    admin must not widen their own access."""
    role = _create_role(
        client, test_store_id, "Shift lead", _matrix(transfers=["read"]),
    )
    h = _admin(client, test_store_id)
    with db_session():
        me_id = (
            db.session.query(User)
            .filter_by(store_id=test_store_id, role="admin")
            .first().id
        )
    resp = client.put(
        f"/api/v2/admin/users/{me_id}/role",
        headers=h, json={"role_id": role["id"]},
    )
    assert resp.status_code == 422
    assert "your own access" in resp.text.lower()


def test_employee_cannot_manage_roles(client, test_store_id):
    from tests.conftest import make_employee_client

    emp_client, token = make_employee_client(test_store_id)
    resp = emp_client.post(
        "/api/v2/admin/roles",
        headers=_headers(token),
        json={"name": "Sneaky", "matrix": _matrix(monthly=["read"])},
    )
    assert resp.status_code == 403
