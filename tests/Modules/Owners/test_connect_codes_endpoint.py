"""HTTP integration tests for owner connect codes + unlink.

  GET    /api/v2/owner/connect-codes
  POST   /api/v2/owner/connect-codes
  POST   /api/v2/owner/connect-codes/{id}/revoke
  POST   /api/v2/owner/unlink/{store_id}

Mirrors the legacy /owner/connect/* + /owner/unlink/<id> form
handlers — JSON envelopes the SPA can render directly.
"""
from datetime import datetime, timedelta
from tests._app import db, db_session


def _make_owner(*, username="boss-cc@x.com", password="ownerpass1!"):
    from api.Modules.Tenancy.Models import Store, User
    from tests._app import db
    s = Store(name="Boss CC Home", slug="boss-cc",
              email=username, plan="basic")
    db.session.add(s); db.session.commit()
    u = User(
        store_id=s.id, username=username, full_name="Boss",
        email=username, role="owner",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id, s.id, password


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


def _link_store(owner_id, store_name="Sibling", store_slug="sibling-cc"):
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    from tests._app import db
    s = Store(name=store_name, slug=store_slug,
              email=f"{store_slug}@x.com", plan="basic")
    db.session.add(s); db.session.commit()
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=s.id))
    db.session.commit()
    return s.id


# ── Auth gating ─────────────────────────────────────────────


def test_list_codes_requires_jwt(client):
    resp = client.get("/api/v2/owner/connect-codes")
    assert resp.status_code == 401


def test_generate_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_revoke_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/owner/connect-codes/1/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_unlink_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/owner/unlink/1",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Generate ────────────────────────────────────────────────


def test_generate_returns_8_char_code(client):
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert len(body["code"]["code"]) == 8
    assert body["code"]["is_redeemed"] is False
    assert body["code"]["is_revoked"] is False
    assert body["code"]["is_expired"] is False


# ── List ────────────────────────────────────────────────────


def test_list_returns_owners_codes(client):
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-cc@x.com", pw)
    # generate two
    client.post(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = client.get(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 2


def test_list_excludes_other_owners_codes(client):
    """Cross-owner isolation: another owner's code mustn't surface."""
    from api.Modules.Tenancy.Models import OwnerConnectCode, User
    from tests._app import db
    with db_session():
        _, _, pw = _make_owner()
        # Seed a different owner with a code
        other = User(
            store_id=None, username="other-cc@x.com",
            full_name="Other", role="owner",
        )
        other.set_password("x")
        db.session.add(other); db.session.commit()
        db.session.add(OwnerConnectCode(
            owner_id=other.id, code="OTHER999",
            expires_at=datetime.utcnow() + timedelta(days=7),
        ))
        db.session.commit()
    token = _login_owner(client, "boss-cc@x.com", pw)
    body = client.get(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    codes = [r["code"] for r in body["rows"]]
    assert "OTHER999" not in codes


def test_list_marks_expired(client):
    from api.Modules.Tenancy.Models import OwnerConnectCode
    from tests._app import db
    with db_session():
        owner_id, _, pw = _make_owner()
        db.session.add(OwnerConnectCode(
            owner_id=owner_id, code="EXPIRED1",
            expires_at=datetime.utcnow() - timedelta(days=1),
        ))
        db.session.commit()
    token = _login_owner(client, "boss-cc@x.com", pw)
    body = client.get(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(r for r in body["rows"] if r["code"] == "EXPIRED1")
    assert row["is_expired"] is True


# ── Revoke ──────────────────────────────────────────────────


def test_revoke_marks_code_revoked(client):
    from api.Modules.Tenancy.Models import OwnerConnectCode
    from tests._app import db
    with db_session():
        owner_id, _, pw = _make_owner()
        c = OwnerConnectCode(
            owner_id=owner_id, code="REVME001",
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.session.add(c); db.session.commit()
        cid = c.id
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/connect-codes/{cid}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["code"]["is_revoked"] is True


def test_revoke_404_for_other_owners_code(client):
    from api.Modules.Tenancy.Models import OwnerConnectCode, User
    from tests._app import db
    with db_session():
        _, _, pw = _make_owner()
        other = User(
            store_id=None, username="x-cc@x.com",
            full_name="X", role="owner",
        )
        other.set_password("x")
        db.session.add(other); db.session.commit()
        c = OwnerConnectCode(
            owner_id=other.id, code="OTHERREV",
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.session.add(c); db.session.commit()
        cid = c.id
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/connect-codes/{cid}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_revoke_409_when_already_redeemed(client):
    from api.Modules.Tenancy.Models import OwnerConnectCode
    from tests._app import db
    with db_session():
        owner_id, _, pw = _make_owner()
        c = OwnerConnectCode(
            owner_id=owner_id, code="USED0001",
            expires_at=datetime.utcnow() + timedelta(days=7),
            used_at=datetime.utcnow(),
        )
        db.session.add(c); db.session.commit()
        cid = c.id
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/connect-codes/{cid}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ── Unlink ──────────────────────────────────────────────────


def test_unlink_removes_link(client):
    from api.Modules.Tenancy.Models import StoreOwnerLink
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, store_name="Linked",
                          store_slug="linked-cc")
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/unlink/{sid}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    from tests._app import db as _db
    with db_session():
        assert db.session.query(StoreOwnerLink).filter_by(
            owner_id=owner_id, store_id=sid,
        ).first() is None


def test_unlink_404_when_not_linked(client):
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        "/api/v2/owner/unlink/9999999",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_unlink_404_for_other_owners_link(client):
    """Trying to unlink a store that's in another owner's umbrella
    returns 404 — the relationship doesn't exist for THIS owner."""
    from api.Modules.Tenancy.Models import StoreOwnerLink, User
    from tests._app import db
    with db_session():
        owner1_id, _, pw = _make_owner()
        # Create a separate owner + their store link
        owner2 = User(
            store_id=None, username="other-link@x.com",
            full_name="O", role="owner",
        )
        owner2.set_password("x")
        db.session.add(owner2); db.session.commit()
        sid = _link_store(owner2.id, store_name="OtherStore",
                          store_slug="other-store-cc")
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/unlink/{sid}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    _ = owner1_id  # silence unused


def test_unlink_rejects_extra_fields(client):
    """Body schema is extra="forbid" — typos must 422."""
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, store_name="Linked",
                          store_slug="linked2-cc")
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/unlink/{sid}",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Owner-audit coverage (invariant #7) ─────────────────────


def _latest_owner_audit(owner_id, action):
    from api.Modules.Audit.Models import OwnerAuditLog
    from tests._app import db
    return (
        db.session.query(OwnerAuditLog)
          .filter_by(owner_id=owner_id, action=action)
          .order_by(OwnerAuditLog.id.desc())
          .first()
    )


def test_generate_records_owner_audit(client):
    with db_session():
        owner_id, _, pw = _make_owner()
    token = _login_owner(client, "boss-cc@x.com", pw)
    resp = client.post(
        "/api/v2/owner/connect-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    with db_session():
        row = _latest_owner_audit(owner_id, "generate_connect_code")
    assert row is not None
    assert row.target_type == "owner_connect_code"
    assert row.owner_name  # snapshot captured


def test_revoke_records_owner_audit_once(client):
    from api.Modules.Tenancy.Models import OwnerConnectCode
    from api.Modules.Audit.Models import OwnerAuditLog
    from tests._app import db
    with db_session():
        owner_id, _, pw = _make_owner()
        c = OwnerConnectCode(
            owner_id=owner_id, code="AUDITREV",
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.session.add(c); db.session.commit()
        cid = c.id
    token = _login_owner(client, "boss-cc@x.com", pw)
    r1 = client.post(
        f"/api/v2/owner/connect-codes/{cid}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    # Re-revoking is a no-op → must NOT append a second audit row.
    client.post(
        f"/api/v2/owner/connect-codes/{cid}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        n = (db.session.query(OwnerAuditLog)
             .filter_by(owner_id=owner_id, action="revoke_connect_code")
             .count())
    assert n == 1
