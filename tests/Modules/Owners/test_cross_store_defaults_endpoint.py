"""HTTP integration tests for the owner cross-store defaults endpoint.

  POST /api/v2/owner/cross-store-defaults

Mirrors the bulk-add-user pattern: a multi-store owner pushes
the same field defaults (fed-tax-rate, timezone, business
hours, etc.) to every store they pick. Per-store outcomes
(updated / rejected) come back in the response.
"""
from tests._app import db, db_session


# ── Helpers ─────────────────────────────────────────────────


def _make_owner(*, username="boss-cs@x.com", password="csopassword1!"):
    from api.Modules.Tenancy.Models import Store, User
    s = Store(
        name="Boss CS Home", slug="boss-cs",
        email=username, plan="basic",
    )
    db.session.add(s); db.session.commit()
    u = User(
        store_id=s.id, username=username, full_name="Boss CS",
        email=username, role="owner",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id, s.id, password


def _link_store(owner_id, *, name="Linked", slug="linked-cs"):
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    s = Store(
        name=name, slug=slug,
        email=f"{slug}@x.com", plan="basic",
    )
    db.session.add(s); db.session.commit()
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=s.id))
    db.session.commit()
    return s.id


def _login_owner(client, username, password):
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


def test_cross_store_defaults_requires_jwt(client):
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={"store_ids": [1], "timezone": "America/Chicago"},
    )
    assert resp.status_code == 401


def test_cross_store_defaults_rejects_admin_role(client, test_store_id):
    """Only owners (or superadmin) can call this — store admins
    use the per-store Settings page instead."""
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={"store_ids": [test_store_id], "timezone": "America/Chicago"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Happy path ──────────────────────────────────────────────


def test_cross_store_defaults_pushes_to_every_umbrella_store(client):
    """Push timezone + fed-tax to two linked stores → both
    updated."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A CS", slug="a-cs")
        sid_b = _link_store(owner_id, name="B CS", slug="b-cs")
    token = _login_owner(client, "boss-cs@x.com", pw)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={
            "store_ids": [sid_a, sid_b],
            "timezone":  "America/Chicago",
            "federal_tax_rate": 0.025,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["updated"]  == 2
    assert body["rejected"] == 0
    assert {r["status"] for r in body["results"]} == {"updated"}
    with db_session():
        for sid in (sid_a, sid_b):
            s = db.session.get(Store, sid)
            assert s.timezone         == "America/Chicago"
            assert s.federal_tax_rate == 0.025


def test_cross_store_defaults_rejects_cross_umbrella_store(client):
    """A store_id outside the owner's umbrella surfaces as
    ``rejected``; the legit store_ids still get updated."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="In", slug="in-cs")
        outsider = Store(
            name="Outsider CS", slug="outsider-cs",
            email="outsider-cs@x.com", plan="basic",
        )
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-cs@x.com", pw)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={
            "store_ids": [sid_a, sid_out],
            "timezone":  "America/New_York",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["updated"]  == 1
    assert body["rejected"] == 1
    by_store = {r["store_id"]: r["status"] for r in body["results"]}
    assert by_store[sid_a]   == "updated"
    assert by_store[sid_out] == "rejected"


def test_cross_store_defaults_surface_field_validation_per_store(client):
    """A bogus timezone string fails the service-layer
    whitelist for every store — each surfaces as a
    ``rejected`` row with the error detail, not a blanket
    4xx."""
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A bogus", slug="a-bogus")
    token = _login_owner(client, "boss-cs@x.com", pw)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={
            "store_ids": [sid_a],
            "timezone":  "Mars/Olympus_Mons",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["updated"]  == 0
    assert body["rejected"] == 1
    assert "Mars" in body["results"][0]["detail"]


def test_cross_store_defaults_rejects_empty_fields(client):
    """An empty body (just store_ids) is a no-op — surface as
    422 rather than touching the DB."""
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A noop", slug="a-noop")
    token = _login_owner(client, "boss-cs@x.com", pw)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={"store_ids": [sid_a]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_cross_store_defaults_writes_audit_rows(client):
    """One audit row per updated store — keeps the per-store
    admin audit-log view consistent with the rest of the
    surface."""
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A audit", slug="a-aud")
        sid_b = _link_store(owner_id, name="B audit", slug="b-aud")
    token = _login_owner(client, "boss-cs@x.com", pw)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={
            "store_ids": [sid_a, sid_b],
            "timezone":  "America/Chicago",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
              .filter(
                  OperatorAuditLog.target_type == "store",
                  OperatorAuditLog.action == "cross_store_update",
                  OperatorAuditLog.store_id.in_([sid_a, sid_b]),
              )
              .all()
        )
        assert len(rows) == 2
        assert all("timezone" in r.summary for r in rows)


def test_cross_store_defaults_rejects_empty_store_ids(client):
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-cs@x.com", pw)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={"store_ids": [], "timezone": "UTC"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_cross_store_defaults_pushes_business_hours_payload(client):
    """Pushing a 7-row business-hours payload goes through the
    same ``validate_hours_payload`` guard the per-store
    settings page uses — bad shapes surface as ``rejected``,
    valid shapes land."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A hours", slug="a-hrs")
    hours = [
        {"day": d, "open": "08:00", "close": "20:00", "closed": False}
        for d in range(7)
    ]
    token = _login_owner(client, "boss-cs@x.com", pw)
    resp = client.post(
        "/api/v2/owner/cross-store-defaults",
        json={"store_ids": [sid_a], "store_hours": hours},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["updated"] == 1
    with db_session():
        s = db.session.get(Store, sid_a)
        assert isinstance(s.store_hours, list)
        assert len(s.store_hours) == 7
        assert s.store_hours[0]["open"] == "08:00"
