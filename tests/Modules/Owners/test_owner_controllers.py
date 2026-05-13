"""HTTP integration tests for the Owners Controllers.

Mounts at /api/v2/owner/*. First slice ships the locations
list — per-store stats for the owner umbrella view.
"""
from datetime import date


def _make_owner(*, username="boss@example.com", password="ownerpass1!",
                home_store_slug="boss-home"):
    """Create an owner User + their home store, return (user_id,
    home_store_id, raw_password). The owner can then be linked to
    additional stores via _link()."""
    from api.Modules.Tenancy.Models import Store, User
    from app import db
    s = Store(name="Boss Home", slug=home_store_slug,
              email=username, plan="basic")
    db.session.add(s); db.session.commit()
    u = User(
        store_id=s.id, username=username, full_name="Big Boss",
        email=username, role="owner",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id, s.id, password


def _link(owner_id, *, store_name="Sibling", store_slug="sibling"):
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    from app import db
    s = Store(name=store_name, slug=store_slug,
              email=f"{store_slug}@x.com", plan="basic")
    db.session.add(s); db.session.commit()
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=s.id))
    db.session.commit()
    return s.id


def _seed_transfer(store_id, *, send_amount=500.0, company="Intermex",
                   send_date_=None):
    from api.Modules.Transfers.Models import Transfer
    from app import db
    t = Transfer(
        store_id=store_id,
        send_date=send_date_ or date.today(),
        company=company, sender_name="x",
        send_amount=send_amount, fee=2.0, federal_tax=0.0,
        status="Sent",
    )
    db.session.add(t); db.session.commit()
    return t.id


def _login_owner(client, username, password):
    """Owners use the cross-store login flow — no store_id needed."""
    resp = client.post(
        "/api/v2/auth/login-cross-store",
        json={"username": username, "password": password},
    )
    return resp.get_json()["access_token"]


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


# ── Auth gating ─────────────────────────────────────────────


def test_locations_requires_jwt(client):
    resp = client.get("/api/v2/owner/locations")
    assert resp.status_code == 401


def test_locations_rejects_admin_role(client, test_store_id):
    """A store admin (non-owner) can't hit owner endpoints."""
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/owner/locations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Happy paths ─────────────────────────────────────────────


def test_locations_returns_empty_envelope_for_unlinked_owner(client):
    """An owner with no StoreOwnerLink rows sees `total=0`."""
    from app import app as flask_app
    with flask_app.app_context():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss@example.com", pw)
    resp = client.get(
        "/api/v2/owner/locations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"rows": [], "total": 0, "matched": 0}


def test_locations_lists_linked_stores_with_period_stats(client):
    from app import app as flask_app
    with flask_app.app_context():
        owner_id, _, pw = _make_owner()
        s1 = _link(owner_id, store_name="Alpha", store_slug="alpha")
        s2 = _link(owner_id, store_name="Beta",  store_slug="beta")
        _seed_transfer(s1, send_amount=100.0)
        _seed_transfer(s1, send_amount=200.0, company="Maxi")
        _seed_transfer(s2, send_amount=400.0)
    token = _login_owner(client, "boss@example.com", pw)
    resp = client.get(
        "/api/v2/owner/locations?period=month",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    assert body["matched"] == 2
    rows = {r["store_slug"]: r for r in body["rows"]}
    assert rows["alpha"]["transfer_count"] == 2
    assert rows["alpha"]["volume"] == 300.0
    assert rows["beta"]["transfer_count"] == 1
    assert rows["beta"]["volume"] == 400.0
    chips = {c["company"]: c for c in rows["alpha"]["companies"]}
    assert chips["Intermex"]["count"] == 1
    assert chips["Maxi"]["count"] == 1


def test_locations_filters_by_query(client):
    from app import app as flask_app
    with flask_app.app_context():
        owner_id, _, pw = _make_owner()
        _link(owner_id, store_name="Alpha", store_slug="alpha")
        _link(owner_id, store_name="Beta",  store_slug="beta")
    token = _login_owner(client, "boss@example.com", pw)
    resp = client.get(
        "/api/v2/owner/locations?q=alp",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    assert body["total"] == 2     # umbrella size unchanged by filter
    assert body["matched"] == 1
    assert body["rows"][0]["store_slug"] == "alpha"


def test_locations_rejects_invalid_period(client):
    from app import app as flask_app
    with flask_app.app_context():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss@example.com", pw)
    resp = client.get(
        "/api/v2/owner/locations?period=garbage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_locations_excludes_unrelated_stores(client):
    """Stores that aren't in the owner's umbrella don't appear, even
    if they have transfers."""
    from app import app as flask_app
    with flask_app.app_context():
        owner_id, _, pw = _make_owner()
        s1 = _link(owner_id, store_name="Mine", store_slug="mine")
        _seed_transfer(s1, send_amount=50.0)
        # Unlinked store — should NOT appear
        from api.Modules.Tenancy.Models import Store
        from app import db
        other = Store(name="Theirs", slug="theirs",
                      email="t@x.com", plan="basic")
        db.session.add(other); db.session.commit()
        _seed_transfer(other.id, send_amount=999.0)
    token = _login_owner(client, "boss@example.com", pw)
    resp = client.get(
        "/api/v2/owner/locations",
        headers={"Authorization": f"Bearer {token}"},
    )
    slugs = {r["store_slug"] for r in resp.get_json()["rows"]}
    assert slugs == {"mine"}
