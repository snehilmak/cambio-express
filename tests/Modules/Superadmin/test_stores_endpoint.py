"""HTTP integration tests for the Superadmin store CRUD endpoints.

Mounts at /api/v2/superadmin/stores. Read + create + update —
mirrors the legacy `/superadmin/stores/new` Flask handler's
contract so the SPA can drive the same form without losing
fields. Auth gating, audit-log emission, slug normalization, and
duplicate-slug 409s are all covered here.
"""
import pytest
from tests._app import db, db_session


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
    """Wraps the SPA two-step login (password → TOTP exchange)."""
    from tests.conftest import login_superadmin
    return login_superadmin(client)


_VALID_CREATE = {
    "name":           "New Branch",
    "slug":           "new-branch",
    "email":          "branch@example.com",
    "phone":          "555-0000",
    "address":        "1 Main St",
    "plan":           "trial",
    "admin_username": "branchadmin",
    "admin_name":     "Branch Admin",
    "admin_password": "branchpass123!",
}


# ── Auth gating ─────────────────────────────────────────────


def test_get_requires_jwt(client, test_store_id):
    resp = client.get(f"/api/v2/superadmin/stores/{test_store_id}")
    assert resp.status_code == 401


def test_get_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/superadmin/stores/{test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_create_requires_jwt(client):
    resp = client.post(
        "/api/v2/superadmin/stores", json=_VALID_CREATE,
    )
    assert resp.status_code == 401


def test_create_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/superadmin/stores",
        json=_VALID_CREATE,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_patch_requires_jwt(client, test_store_id):
    resp = client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"name": "Renamed"},
    )
    assert resp.status_code == 401


def test_patch_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"name": "Renamed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── GET detail ──────────────────────────────────────────────


def test_get_returns_full_payload(client, test_store_id):
    token = _login_superadmin(client)
    resp = client.get(
        f"/api/v2/superadmin/stores/{test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    s = body["store"]
    assert s["store_id"] == test_store_id
    assert s["name"] == "Test Store"
    assert s["slug"] == "test-store"
    # Edit-form fields not in the list-view row
    assert "address" in s
    assert "federal_tax_rate" in s


def test_get_404_for_unknown_store(client):
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/stores/999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── POST create ─────────────────────────────────────────────


def test_create_happy_path(client):
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/superadmin/stores",
        json=_VALID_CREATE,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["store"]["slug"] == "new-branch"
    assert body["store"]["name"] == "New Branch"
    with db_session():
        s = db.session.query(Store).filter_by(slug="new-branch").first()
        assert s is not None
        assert s.plan == "trial"
        assert s.email == "branch@example.com"


def test_create_records_audit(client):
    from api.Modules.Audit.Models import SuperadminAuditLog
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    client.post(
        "/api/v2/superadmin/stores",
        json=_VALID_CREATE,
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        s = db.session.query(Store).filter_by(slug="new-branch").first()
        row = (
            SuperadminAuditLog.query
            .filter_by(action="create_store", target_id=str(s.id))
            .first()
        )
        assert row is not None
        assert row.target_type == "store"
        assert row.details == "new-branch"


def test_create_seeds_admin_user(client):
    from api.Modules.Tenancy.Models import Store, User
    token = _login_superadmin(client)
    client.post(
        "/api/v2/superadmin/stores",
        json=_VALID_CREATE,
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        s = db.session.query(Store).filter_by(slug="new-branch").first()
        admin = db.session.query(User).filter_by(store_id=s.id, role="admin").first()
        assert admin is not None
        assert admin.username == "branchadmin"
        assert admin.full_name == "Branch Admin"
        # Password persisted as a hash, never plaintext.
        assert admin.password_hash != "branchpass123!"
        assert admin.check_password("branchpass123!")


def test_create_normalizes_slug(client):
    """Slug should be lowercased + spaces-to-dashes, mirroring the
    legacy Flask handler's `slug.strip().lower().replace(" ","-")`."""
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    payload = dict(_VALID_CREATE, slug="My New BRANCH")
    resp = client.post(
        "/api/v2/superadmin/stores",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["store"]["slug"] == "my-new-branch"
    with db_session():
        assert db.session.query(Store).filter_by(slug="my-new-branch").first() is not None


def test_create_rejects_duplicate_slug(client):
    """Existing slug returns 409 with a field-level error envelope
    so the SPA can render `Slug 'X' is already taken` inline."""
    from api.Modules.Audit.Models import SuperadminAuditLog
    token = _login_superadmin(client)
    client.post(
        "/api/v2/superadmin/stores",
        json=_VALID_CREATE,
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.post(
        "/api/v2/superadmin/stores",
        json={**_VALID_CREATE, "name": "Other Store"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    detail = resp.get_json().get("detail")
    assert isinstance(detail, dict)
    assert detail["field"] == "slug"
    assert "already taken" in detail["message"]
    # The duplicate POST must NOT have produced a second audit row.
    with db_session():
        rows = (
            SuperadminAuditLog.query
            .filter_by(action="create_store")
            .all()
        )
        assert len(rows) == 1


def test_create_rejects_empty_name(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/superadmin/stores",
        json={**_VALID_CREATE, "name": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_invalid_plan(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/superadmin/stores",
        json={**_VALID_CREATE, "plan": "enterprise"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_extra_fields(client):
    """Schema is extra=forbid — typos must 422."""
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/superadmin/stores",
        json={**_VALID_CREATE, "color": "neon"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_requires_admin_password(client):
    """The legacy form fell back to a hard-coded "changeme123!" — we
    deliberately drop that footgun. Missing admin_password is 422."""
    token = _login_superadmin(client)
    payload = {k: v for k, v in _VALID_CREATE.items() if k != "admin_password"}
    resp = client.post(
        "/api/v2/superadmin/stores",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_admin_user_defaults_when_omitted(client):
    """If admin_username + admin_name are omitted, the endpoint
    falls back to the legacy defaults ("admin" / "Store Admin")."""
    from api.Modules.Tenancy.Models import Store, User
    token = _login_superadmin(client)
    payload = {
        "name": "Defaulted Branch", "slug": "defaulted",
        "admin_password": "x" * 12,
    }
    resp = client.post(
        "/api/v2/superadmin/stores",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    with db_session():
        s = db.session.query(Store).filter_by(slug="defaulted").first()
        admin = db.session.query(User).filter_by(store_id=s.id, role="admin").first()
        assert admin.username == "admin"
        assert admin.full_name == "Store Admin"


# ── PATCH update ────────────────────────────────────────────


def test_patch_updates_identity_fields(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    resp = client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"name": "Renamed Store", "phone": "+1 555 999 8888"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["store"]["name"] == "Renamed Store"
    assert body["store"]["phone"] == "+1 555 999 8888"
    with db_session():
        s = db.session.query(Store).filter_by(id=test_store_id).first()
        assert s.name == "Renamed Store"
        assert s.phone == "+1 555 999 8888"


def test_patch_records_audit_with_changed_keys(client, test_store_id):
    from api.Modules.Audit.Models import SuperadminAuditLog
    token = _login_superadmin(client)
    client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"name": "Renamed Store", "email": "new@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        row = (
            SuperadminAuditLog.query
            .filter_by(action="update_store", target_id=str(test_store_id))
            .first()
        )
        assert row is not None
        # `details` is the comma-separated changed-keys list so the
        # audit log shows what was touched without leaking values.
        keys = set(row.details.split(","))
        assert keys == {"name", "email"}


def test_patch_no_op_skips_audit(client, test_store_id):
    """PATCH with all-current values shouldn't record an audit row —
    a no-op shouldn't pollute the audit log."""
    from api.Modules.Audit.Models import SuperadminAuditLog
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    with db_session():
        s = db.session.query(Store).filter_by(id=test_store_id).first()
        same_payload = {"name": s.name, "slug": s.slug, "email": s.email or ""}
    client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json=same_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        rows = (
            SuperadminAuditLog.query
            .filter_by(action="update_store")
            .all()
        )
        assert rows == []


def test_patch_404_for_unknown_store(client):
    token = _login_superadmin(client)
    resp = client.patch(
        "/api/v2/superadmin/stores/999999",
        json={"name": "Ghost"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_patch_rejects_duplicate_slug(client, test_store_id):
    """Renaming to a slug another store already owns returns 409."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    token = _login_superadmin(client)
    with db_session():
        other = Store(name="Other", slug="other-store", plan="trial")
        db.session.add(other); db.session.commit()
    resp = client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"slug": "other-store"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    detail = resp.get_json().get("detail")
    assert isinstance(detail, dict)
    assert detail["field"] == "slug"


def test_patch_normalizes_slug(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    resp = client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"slug": "My RENAMED Store"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    with db_session():
        s = db.session.query(Store).filter_by(id=test_store_id).first()
        assert s.slug == "my-renamed-store"


def test_patch_rejects_invalid_plan(client, test_store_id):
    token = _login_superadmin(client)
    resp = client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"plan": "enterprise"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_patch_updates_federal_tax_rate(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    resp = client.patch(
        f"/api/v2/superadmin/stores/{test_store_id}",
        json={"federal_tax_rate": 0.0825},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    with db_session():
        s = db.session.query(Store).filter_by(id=test_store_id).first()
        assert abs(s.federal_tax_rate - 0.0825) < 1e-6


# ── Flask 301 redirect ──────────────────────────────────────


@pytest.fixture
def _superadmin_flask_client():
    """Test client for the legacy ``/superadmin/stores/new`` URLs.
    These are SPA-cutover redirects (301 → ``/app/...``) — they
    don't depend on session/JWT auth, so we use the standard
    ``AsgiTestClient`` for transport parity with production."""
    from tests.conftest import AsgiTestClient
    return AsgiTestClient()


def test_legacy_new_get_redirects_301(_superadmin_flask_client):
    resp = _superadmin_flask_client.get(
        "/superadmin/stores/new", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/app/superadmin/stores/new")


def test_legacy_new_post_redirects_301(_superadmin_flask_client):
    """The legacy POST handler used to create the store. After the
    SPA migration it 301s — the SPA POSTs to /api/v2 directly."""
    resp = _superadmin_flask_client.post(
        "/superadmin/stores/new",
        data=_VALID_CREATE,
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/app/superadmin/stores/new")
