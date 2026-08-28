"""Owner store-switching (U-2 — single-dashboard principle).

The invariants under test (see Auth INVARIANTS.md):
  * /auth/my-stores lists the owner's umbrella (links ∪ home
    store), flagging the current token's store,
  * /auth/switch-store issues a store-scoped ADMIN token whose
    sub stays the owner (audit attribution) with the owner_id
    context marker — and the token actually works on admin
    surfaces of the target store,
  * re-switching from an owner-context token works (owner_id path),
  * stores outside the umbrella 404; admins/employees 403,
  * every switch writes an owner_enter_store audit row at the
    target store.
"""
from tests._app import db, db_session


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_owner(username="switch-boss@example.com", password="ownerpass1!"):
    from api.Modules.Tenancy.Models import Store, User
    with db_session():
        home = Store(name="Boss Home", slug="switch-boss-home",
                     email=username, plan="basic",
                     address="1 Main St, Austin, TX")
        db.session.add(home); db.session.commit()
        u = User(store_id=home.id, username=username,
                 full_name="Big Boss", email=username, role="owner")
        u.set_password(password)
        db.session.add(u); db.session.commit()
        return u.id, home.id, username, password


def _link_store(owner_id, slug, name):
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    with db_session():
        s = Store(name=name, slug=slug, email=f"{slug}@x.com",
                  plan="basic", address=f"{name} Rd, Austin, TX")
        db.session.add(s); db.session.commit()
        db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=s.id))
        db.session.commit()
        return s.id


def _login_owner(client, username, password):
    resp = client.post("/api/v2/auth/login-cross-store", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_my_stores_and_switch_roundtrip(client):
    owner_id, home_id, username, password = _make_owner()
    sib_id = _link_store(owner_id, "switch-sib", "Los Hermanos")
    token = _login_owner(client, username, password)

    body = client.get("/api/v2/auth/my-stores", headers=_headers(token)).json()
    by_id = {s["store_id"]: s for s in body["stores"]}
    assert set(by_id) == {home_id, sib_id}
    assert by_id[sib_id]["name"] == "Los Hermanos"
    assert by_id[sib_id]["address"].startswith("Los Hermanos Rd")

    # Enter the sibling store → store-scoped ADMIN token.
    resp = client.post("/api/v2/auth/switch-store", headers=_headers(token),
                       json={"store_id": sib_id})
    assert resp.status_code == 200, resp.text
    switched = resp.json()
    assert switched["role"] == "admin"
    assert switched["store_id"] == sib_id
    assert switched["store_name"] == "Los Hermanos"
    admin_token = switched["access_token"]

    # The derived token works on an admin surface of that store…
    h = _headers(admin_token)
    assert client.get(
        "/api/v2/dayclose/departments", headers=h,
    ).status_code == 200
    # …and session-status reflects the entered store.
    status = client.get("/api/v2/auth/session-status", headers=h).json()
    assert status["store_name"] == "Los Hermanos"

    # my-stores from the derived token flags the current store and
    # allows re-switching (owner_id claim path).
    body2 = client.get("/api/v2/auth/my-stores", headers=h).json()
    flags = {s["store_id"]: s["is_current"] for s in body2["stores"]}
    assert flags[sib_id] is True and flags[home_id] is False
    resp2 = client.post("/api/v2/auth/switch-store", headers=h,
                        json={"store_id": home_id})
    assert resp2.status_code == 200
    assert resp2.json()["store_id"] == home_id

    # Audit: owner_enter_store rows at both target stores, sub=owner.
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
            .filter_by(action="owner_enter_store")
            .all()
        )
        assert {(r.store_id, r.user_id) for r in rows} >= {
            (sib_id, owner_id), (home_id, owner_id),
        }


def test_switch_outside_umbrella_404(client, test_store_id):
    _, _, username, password = _make_owner(
        username="lonely-boss@example.com",
    )
    token = _login_owner(client, username, password)
    # test_store_id belongs to the fixture store, not this owner.
    resp = client.post("/api/v2/auth/switch-store", headers=_headers(token),
                       json={"store_id": test_store_id})
    assert resp.status_code == 404


def test_non_owner_cannot_switch(client, test_store_id):
    from tests.conftest import login_admin
    token = login_admin(client, test_store_id)
    assert client.get(
        "/api/v2/auth/my-stores", headers=_headers(token),
    ).status_code == 403
    assert client.post(
        "/api/v2/auth/switch-store", headers=_headers(token),
        json={"store_id": test_store_id},
    ).status_code == 403
