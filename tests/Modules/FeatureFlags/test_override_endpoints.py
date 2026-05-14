"""HTTP integration tests for the per-store FeatureFlag override
endpoints.

  GET    /api/v2/feature-flags/{key}/overrides
  PUT    /api/v2/feature-flags/{key}/stores/{store_id}
  DELETE /api/v2/feature-flags/{key}/stores/{store_id}

Mirrors the legacy /superadmin/features/{key}/stores/{store_id}
form handler. Superadmin-scoped.
"""
from tests._app import db


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


def _login_superadmin(client):
    """Wraps the SPA two-step login (password → TOTP exchange)
    using the seeded superadmin's pre-enrolled TOTP secret. See
    tests/conftest.py for the secret + helper definition."""
    from tests.conftest import login_superadmin
    return login_superadmin(client)


def _seed_flag(key="bank_sync"):
    from api.Modules.Billing.Models import FeatureFlag
    from tests._app import db
    f = FeatureFlag(key=key, label=key, enabled_by_default=True)
    db.session.add(f); db.session.commit()
    return f.id


def _seed_override(store_id, key, enabled):
    from api.Modules.Billing.Models import StoreFeatureOverride
    from tests._app import db
    o = StoreFeatureOverride(
        store_id=store_id, flag_key=key, enabled=enabled,
    )
    db.session.add(o); db.session.commit()
    return o.id


# ── Auth ────────────────────────────────────────────────────


def test_list_overrides_requires_jwt(client):
    resp = client.get("/api/v2/feature-flags/x/overrides")
    assert resp.status_code == 401


def test_upsert_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.put(
        f"/api/v2/feature-flags/x/stores/{test_store_id}",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_clear_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.delete(
        f"/api/v2/feature-flags/x/stores/{test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Upsert ──────────────────────────────────────────────────


def test_upsert_creates_override(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="bank_sync")
    token = _login_superadmin(client)
    resp = client.put(
        f"/api/v2/feature-flags/bank_sync/stores/{test_store_id}",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["override"]["flag_key"] == "bank_sync"
    assert body["override"]["enabled"] is False


def test_upsert_updates_existing_override(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="bank_sync")
        _seed_override(test_store_id, "bank_sync", enabled=False)
    token = _login_superadmin(client)
    resp = client.put(
        f"/api/v2/feature-flags/bank_sync/stores/{test_store_id}",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["override"]["enabled"] is True


def test_upsert_404_when_flag_missing(client, test_store_id):
    token = _login_superadmin(client)
    resp = client.put(
        f"/api/v2/feature-flags/nonexistent/stores/{test_store_id}",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_upsert_404_when_store_missing(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="bank_sync")
    token = _login_superadmin(client)
    resp = client.put(
        "/api/v2/feature-flags/bank_sync/stores/999999",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── List + clear ────────────────────────────────────────────


def test_list_returns_per_store_rows(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        _seed_flag(key="bank_sync")
        s2 = Store(name="Beta", slug="beta-flag",
                   email="b@x.com", plan="basic")
        db.session.add(s2); db.session.commit()
        _seed_override(test_store_id, "bank_sync", enabled=True)
        _seed_override(s2.id, "bank_sync", enabled=False)
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/feature-flags/bank_sync/overrides",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 2
    slugs = [r["store_slug"] for r in body["rows"]]
    # Sorted by store_name lowercased: Beta < Test Store
    assert slugs[0] == "beta-flag"


def test_list_empty_for_unknown_flag(client):
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/feature-flags/nonexistent/overrides",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body == {"rows": [], "total": 0}


def test_clear_removes_override(client, test_store_id):
    from api.Modules.Billing.Models import StoreFeatureOverride
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="bank_sync")
        _seed_override(test_store_id, "bank_sync", enabled=False)
    token = _login_superadmin(client)
    resp = client.delete(
        f"/api/v2/feature-flags/bank_sync/stores/{test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        assert db.session.query(StoreFeatureOverride).filter_by(
            store_id=test_store_id, flag_key="bank_sync",
        ).first() is None


def test_clear_404_when_no_override(client, test_store_id):
    token = _login_superadmin(client)
    resp = client.delete(
        f"/api/v2/feature-flags/bank_sync/stores/{test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Audit ───────────────────────────────────────────────────


def test_upsert_records_audit_entry(client, test_store_id):
    from api.Modules.Audit.Models import SuperadminAuditLog
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="audit_target")
    token = _login_superadmin(client)
    client.put(
        f"/api/v2/feature-flags/audit_target/stores/{test_store_id}",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    with flask_app.app_context():
        rows = db.session.query(SuperadminAuditLog).filter_by(
            action="set_feature_override",
        ).all()
        assert len(rows) >= 1
