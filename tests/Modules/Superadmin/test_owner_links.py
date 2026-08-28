"""Superadmin concierge onboarding (U-5b): create a store whose
initial user is an OWNER, and connect/disconnect existing owner
logins to stores on the customer's instruction."""
from tests._app import db, db_session
from tests.conftest import login_superadmin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _mk_owner(username, home_store_id=None):
    from api.Modules.Tenancy.Models import StoreOwnerLink, User
    with db_session():
        u = User(
            store_id=home_store_id, username=username,
            full_name="Concierge Owner", role="owner", is_active=True,
        )
        u.set_password("ownerpass1!")
        db.session.add(u)
        db.session.flush()
        if home_store_id is not None:
            db.session.add(StoreOwnerLink(
                owner_id=u.id, store_id=home_store_id,
            ))
        db.session.commit()
        return u.id


def test_create_store_with_initial_owner(client):
    """initial_role=owner mirrors self-service signup: the created
    user is role=owner with the store as home + a link row."""
    token = login_superadmin(client)
    resp = client.post(
        "/api/v2/superadmin/stores",
        headers=_headers(token),
        json={
            "name": "Concierge Mart",
            "slug": "concierge-mart",
            "admin_username": "concierge@example.com",
            "admin_password": "conciergepw1!",
            "initial_role": "owner",
            "business_type": "gas_station",
        },
    )
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    store_id = resp.get_json()["store"]["store_id"]

    from api.Modules.Tenancy.Models import StoreOwnerLink, User
    with db_session():
        u = db.session.query(User).filter_by(
            username="concierge@example.com",
        ).one()
        assert u.role == "owner"
        assert u.store_id == store_id
        assert db.session.query(StoreOwnerLink).filter_by(
            owner_id=u.id, store_id=store_id,
        ).first() is not None

    # The provisioned owner can log in and enter the store.
    login = client.post(
        "/api/v2/auth/login-cross-store",
        json={
            "username": "concierge@example.com",
            "password": "conciergepw1!",
        },
    )
    assert login.status_code == 200
    otoken = login.get_json()["access_token"]
    entered = client.post(
        "/api/v2/auth/switch-store",
        headers=_headers(otoken),
        json={"store_id": store_id},
    )
    assert entered.status_code == 200
    assert entered.get_json()["role"] == "admin"


def test_owner_links_add_and_remove(client, test_store_id):
    """Connect an existing owner to the seeded store, list it,
    then disconnect. Unknown usernames 404; duplicates 409."""
    owner_id = _mk_owner("linkable-owner@example.com")
    token = login_superadmin(client)
    base = f"/api/v2/superadmin/stores/{test_store_id}/owner-links"

    listed = client.get(base, headers=_headers(token))
    assert listed.status_code == 200
    before = {r["owner_id"] for r in listed.get_json()["rows"]}
    assert owner_id not in before

    added = client.post(
        base, headers=_headers(token),
        json={"owner_username": "Linkable-Owner@Example.com"},
    )
    assert added.status_code == 201, added.get_data(as_text=True)
    rows = added.get_json()["rows"]
    assert owner_id in {r["owner_id"] for r in rows}

    dup = client.post(
        base, headers=_headers(token),
        json={"owner_username": "linkable-owner@example.com"},
    )
    assert dup.status_code == 409

    ghost = client.post(
        base, headers=_headers(token),
        json={"owner_username": "nobody@example.com"},
    )
    assert ghost.status_code == 404

    removed = client.delete(
        f"{base}/{owner_id}", headers=_headers(token),
    )
    assert removed.status_code == 200
    assert owner_id not in {
        r["owner_id"] for r in removed.get_json()["rows"]
    }

    # Audit rows for both mutations (invariant #7).
    from api.Modules.Audit.Models import SuperadminAuditLog
    with db_session():
        actions = {
            r.action for r in db.session.query(SuperadminAuditLog)
            .filter(SuperadminAuditLog.target_id == str(test_store_id))
            .all()
        }
        assert {"link_owner", "unlink_owner"} <= actions


def test_owner_links_home_store_guard(client):
    """The link to an owner's HOME store can't be removed — it's
    the account's anchor."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = Store(name="Anchor Store", slug="anchor-store")
        db.session.add(s)
        db.session.commit()
        sid = s.id
    owner_id = _mk_owner("anchored-owner@example.com", home_store_id=sid)
    token = login_superadmin(client)
    resp = client.delete(
        f"/api/v2/superadmin/stores/{sid}/owner-links/{owner_id}",
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_owner_links_reject_non_superadmin(client, test_store_id):
    from tests.conftest import login_admin
    token = login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/superadmin/stores/{test_store_id}/owner-links",
        headers=_headers(token),
    )
    assert resp.status_code in (401, 403)
