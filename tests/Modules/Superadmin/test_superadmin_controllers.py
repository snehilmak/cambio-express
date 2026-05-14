"""HTTP integration tests for the Superadmin Controllers.

Mounts at /api/v2/superadmin/*. First slice ships the stores list.
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


# ── Auth gating ─────────────────────────────────────────────


def test_stores_requires_jwt(client):
    resp = client.get("/api/v2/superadmin/stores")
    assert resp.status_code == 401


def test_stores_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/superadmin/stores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Happy paths ─────────────────────────────────────────────


def test_stores_returns_seeded_test_store(client, test_store_id):
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/stores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] >= 1
    slugs = {r["slug"] for r in body["rows"]}
    assert "test-store" in slugs
    seeded = next(r for r in body["rows"] if r["slug"] == "test-store")
    assert seeded["plan"] == "trial"
    assert seeded["is_active"] is True
    assert seeded["store_id"] == test_store_id


def test_stores_lists_multiple_in_created_desc(client, test_store_id):
    """Creation order — newest first."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        db.session.add(Store(name="Alpha", slug="alpha", plan="basic"))
        db.session.add(Store(name="Beta",  slug="beta",  plan="pro"))
        db.session.commit()
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/stores",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    slugs = [r["slug"] for r in body["rows"]]
    # newest first; the two we just inserted should both appear after
    # the seeded test-store row was created (test-store is older).
    assert "alpha" in slugs
    assert "beta" in slugs
    assert slugs.index("beta") < slugs.index("test-store")
    assert slugs.index("alpha") < slugs.index("test-store")


def test_stores_includes_billing_and_retention_fields(client, test_store_id):
    """Confirm the response carries the fields the UI needs to
    render the trial/billing/retention cells without a follow-up
    fetch."""
    _ = test_store_id
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/stores",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = body["rows"][0]
    assert {
        "store_id", "name", "slug", "email", "phone", "plan",
        "billing_cycle", "is_active", "created_at",
        "trial_ends_at", "grace_ends_at", "data_retention_until",
        "stripe_customer_id", "stripe_subscription_id",
    } == set(row.keys())


# ── /superadmin/audit-log ────────────────────────────────────


def _seed_audit(action="extend_trial", target_type="store", target_id="42",
                details="", admin_name="Super Admin"):
    from api.Modules.Audit.Models import SuperadminAuditLog
    from tests._app import db
    row = SuperadminAuditLog(
        admin_id=None, admin_name=admin_name,
        action=action, target_type=target_type, target_id=target_id,
        details=details,
    )
    db.session.add(row); db.session.commit()
    return row.id


def test_audit_log_requires_jwt(client):
    resp = client.get("/api/v2/superadmin/audit-log")
    assert resp.status_code == 401


def test_audit_log_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/superadmin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_audit_log_returns_paginated_envelope(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        for i in range(3):
            _seed_audit(action=f"act_{i}")
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {
        "rows", "total", "page", "per_page", "total_pages",
    }
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["per_page"] == 50
    assert body["total_pages"] == 1


def test_audit_log_orders_newest_first(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        oldest = _seed_audit(action="oldest")
        newest = _seed_audit(action="newest")
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    ids = [r["id"] for r in body["rows"]]
    assert ids[0] == newest
    assert ids[-1] == oldest


def test_audit_log_filters_by_action(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _seed_audit(action="extend_trial")
        _seed_audit(action="comp_plan")
        _seed_audit(action="extend_trial")
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/audit-log?action=extend",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 2
    assert all("extend" in r["action"] for r in body["rows"])


def test_audit_log_pagination(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        for i in range(5):
            _seed_audit(action=f"act_{i}")
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/audit-log?page=2&per_page=2",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["total_pages"] == 3
    assert len(body["rows"]) == 2
