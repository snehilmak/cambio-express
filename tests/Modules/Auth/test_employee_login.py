"""Unified sign-in: every role uses the same page, and a username
shared across stores resolves by password rather than by row order.

Covers the reported bug — a store admin creates an employee login,
the employee tries to sign in, and the API answers "Please use your
store's sign-in page" for a page that no longer exists.

  POST /api/v2/auth/login-cross-store
"""
from tests._app import db, db_session


def _make_store(slug, name=None):
    from api.Modules.Tenancy.Models import Store
    s = Store(name=name or slug, slug=slug, email=f"{slug}@x.com",
              plan="basic")
    db.session.add(s); db.session.commit()
    return s.id


def _make_user(store_id, username, password, *, role="employee",
               is_active=True, full_name="Person"):
    from api.Modules.Tenancy.Models import User
    u = User(store_id=store_id, username=username, full_name=full_name,
             email=f"{username}@x.com", role=role, is_active=is_active)
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id


def _login(client, username, password):
    return client.post(
        "/api/v2/auth/login-cross-store",
        json={"username": username, "password": password},
    )


# ── The reported bug ────────────────────────────────────────


def test_employee_can_sign_in_on_the_unified_page(client):
    """An employee login created by a store admin must work on the
    same sign-in page everyone else uses. This used to 401 with
    "Please use your store's sign-in page" — a slug-scoped page the
    SPA no longer has, so the account was unusable."""
    with db_session():
        sid = _make_store("emp-login-store", "Emp Login Store")
        _make_user(sid, "amber", "cashierpw1!", role="employee")
    resp = _login(client, "amber", "cashierpw1!")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["role"] == "employee"
    assert body["store_id"] == sid
    assert body["access_token"]


def test_employee_login_is_recorded_for_dau(client):
    """The cross-store route didn't record LoginEvents, so once the
    SPA moved everyone onto it, DAU/MAU went dark."""
    from api.Modules.Auth.Models import LoginEvent
    with db_session():
        sid = _make_store("emp-dau-store")
        uid = _make_user(sid, "dau-emp", "cashierpw1!")
    assert _login(client, "dau-emp", "cashierpw1!").status_code == 200
    with db_session():
        events = (
            db.session.query(LoginEvent)
            .filter(LoginEvent.user_id == uid).all()
        )
        assert len(events) == 1
        assert events[0].role == "employee"


def test_admin_and_owner_still_sign_in(client):
    """Opening the door to employees must not change the roles that
    already worked."""
    with db_session():
        sid = _make_store("emp-roles-store")
        _make_user(sid, "boss-role@x.com", "adminpw123!", role="admin")
    resp = _login(client, "boss-role@x.com", "adminpw123!")
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "admin"


# ── Per-store usernames colliding across stores ─────────────


def test_same_username_at_two_stores_resolves_by_password(client):
    """Usernames are unique per STORE, so "amber" can exist at
    several. The old lookup took the first matching row, so the
    second Amber could never sign in — her password was checked
    against the first Amber's hash. Both must work."""
    with db_session():
        sid_a = _make_store("collide-a", "Store A")
        sid_b = _make_store("collide-b", "Store B")
        _make_user(sid_a, "amber", "amber-a-pw1!")
        _make_user(sid_b, "amber", "amber-b-pw1!")

    first = _login(client, "amber", "amber-a-pw1!")
    assert first.status_code == 200
    assert first.get_json()["store_id"] == sid_a

    # The row that used to be unreachable.
    second = _login(client, "amber", "amber-b-pw1!")
    assert second.status_code == 200
    assert second.get_json()["store_id"] == sid_b


def test_identical_credentials_at_two_stores_ask_which_store(client):
    """Same username AND same password at two stores is genuinely
    ambiguous — answer with the choices instead of guessing."""
    with db_session():
        sid_a = _make_store("twin-a", "Twin A")
        sid_b = _make_store("twin-b", "Twin B")
        _make_user(sid_a, "twin", "sharedpw123!")
        _make_user(sid_b, "twin", "sharedpw123!")

    resp = _login(client, "twin", "sharedpw123!")
    assert resp.status_code == 409
    detail = resp.get_json()["detail"]
    assert detail["code"] == "store_ambiguous"
    assert {s["store_id"] for s in detail["stores"]} == {sid_a, sid_b}
    assert {s["store_name"] for s in detail["stores"]} == {
        "Twin A", "Twin B",
    }


def test_ambiguous_login_resolves_via_explicit_store_id(client):
    """The choice the picker sends back completes the sign-in."""
    with db_session():
        sid_a = _make_store("pick-a", "Pick A")
        sid_b = _make_store("pick-b", "Pick B")
        _make_user(sid_a, "picker", "sharedpw123!")
        _make_user(sid_b, "picker", "sharedpw123!")
    assert _login(client, "picker", "sharedpw123!").status_code == 409
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "picker", "password": "sharedpw123!",
            "store_id": sid_a,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["store_id"] == sid_a


def test_ambiguity_never_leaks_stores_to_a_wrong_password(client):
    """The store list is only returned to someone who already holds
    working credentials — a bad password gets the same opaque 401 as
    an unknown username, revealing nothing about where the name
    exists."""
    with db_session():
        sid_a = _make_store("leak-a", "Leak A")
        sid_b = _make_store("leak-b", "Leak B")
        _make_user(sid_a, "leaky", "realpw12345!")
        _make_user(sid_b, "leaky", "realpw12345!")

    resp = _login(client, "leaky", "wrong-password")
    assert resp.status_code == 401
    body = resp.get_json()
    assert "stores" not in str(body)
    assert body["detail"] == "Invalid username or password"


# ── Inactive / disabled accounts ────────────────────────────


def test_deactivated_employee_cannot_sign_in(client):
    with db_session():
        sid = _make_store("inactive-store")
        _make_user(sid, "gone", "cashierpw1!", is_active=False)
    resp = _login(client, "gone", "cashierpw1!")
    assert resp.status_code == 401
    assert resp.get_json()["detail"] == "Invalid username or password"


def test_deactivating_one_of_two_disambiguates(client):
    """An inactive row is not a candidate, so deactivating the twin
    turns an ambiguous sign-in back into a clean one."""
    with db_session():
        from api.Modules.Tenancy.Models import User
        sid_a = _make_store("deact-a", "Deact A")
        sid_b = _make_store("deact-b", "Deact B")
        _make_user(sid_a, "dual", "sharedpw123!")
        uid_b = _make_user(sid_b, "dual", "sharedpw123!")
        assert _login(client, "dual", "sharedpw123!").status_code == 409
        db.session.get(User, uid_b).is_active = False
        db.session.commit()

    resp = _login(client, "dual", "sharedpw123!")
    assert resp.status_code == 200
    assert resp.get_json()["store_id"] == sid_a


def test_wrong_password_is_opaque(client):
    with db_session():
        sid = _make_store("opaque-store")
        _make_user(sid, "opaque", "cashierpw1!")
    resp = _login(client, "opaque", "nope")
    assert resp.status_code == 401
    assert resp.get_json()["detail"] == "Invalid username or password"


def test_unknown_username_is_opaque(client):
    resp = _login(client, "nobody-here-at-all", "whatever123!")
    assert resp.status_code == 401
    assert resp.get_json()["detail"] == "Invalid username or password"
