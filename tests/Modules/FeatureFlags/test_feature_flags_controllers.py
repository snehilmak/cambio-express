"""HTTP integration tests for the FeatureFlags Controllers."""


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


def _seed_flag(key="bank_sync", label="Bank sync",
               enabled_by_default=True):
    from app import FeatureFlag, db
    f = FeatureFlag(
        key=key, label=label,
        enabled_by_default=enabled_by_default,
    )
    db.session.add(f); db.session.commit()
    return f.id


# ── Auth gating ─────────────────────────────────────────────


def test_list_requires_jwt(client):
    resp = client.get("/api/v2/feature-flags")
    assert resp.status_code == 401


def test_list_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/feature-flags",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_create_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/feature-flags",
        json={"key": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Schema validation ───────────────────────────────────────


def test_create_rejects_invalid_key_pattern(client):
    """Key must be slug-style (lowercase letters, digits, underscores)."""
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/feature-flags",
        json={"key": "Bad-KEY"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_extra_fields(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/feature-flags",
        json={"key": "ok", "rogue": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_duplicate_key(client):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="bank_sync")
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/feature-flags",
        json={"key": "bank_sync", "label": "duplicate"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["detail"]["field"] == "key"


# ── Happy paths ─────────────────────────────────────────────


def test_create_persists_and_returns_row(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/feature-flags",
        json={"key": "addon_tv_display", "label": "TV display",
              "description": "Optional TV add-on", "enabled_by_default": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    flag = resp.get_json()["flag"]
    assert flag["key"] == "addon_tv_display"
    assert flag["enabled_by_default"] is False


def test_list_returns_alphabetic_by_key(client):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="zeta")
        _seed_flag(key="alpha")
        _seed_flag(key="mu")
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/feature-flags",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    keys = [r["key"] for r in body["rows"]]
    assert keys == ["alpha", "mu", "zeta"]


def test_toggle_flips_default(client):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_flag(key="bank_sync", enabled_by_default=True)
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/feature-flags/bank_sync/toggle",
        json={"enabled_by_default": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["flag"]["enabled_by_default"] is False


def test_toggle_404_when_missing(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/feature-flags/nonexistent/toggle",
        json={"enabled_by_default": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_removes_row(client):
    from app import app as flask_app, FeatureFlag
    with flask_app.app_context():
        _seed_flag(key="zap_me")
    token = _login_superadmin(client)
    resp = client.delete(
        "/api/v2/feature-flags/zap_me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        assert FeatureFlag.query.filter_by(key="zap_me").first() is None


def test_delete_cascades_per_store_overrides(client, test_store_id):
    """Deleting a flag cascades the per-store overrides — they
    reference the key string directly and would orphan otherwise."""
    from app import app as flask_app, FeatureFlag, StoreFeatureOverride, db
    with flask_app.app_context():
        _seed_flag(key="targeted")
        db.session.add(StoreFeatureOverride(
            store_id=test_store_id, flag_key="targeted", enabled=True,
        ))
        db.session.commit()
    token = _login_superadmin(client)
    resp = client.delete(
        "/api/v2/feature-flags/targeted",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        assert StoreFeatureOverride.query.filter_by(
            flag_key="targeted",
        ).first() is None


def test_delete_404_when_missing(client):
    token = _login_superadmin(client)
    resp = client.delete(
        "/api/v2/feature-flags/nonexistent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Audit log integration ───────────────────────────────────


def test_create_records_audit_entry(client):
    from app import app as flask_app, SuperadminAuditLog
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/feature-flags",
        json={"key": "audited_flag"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    with flask_app.app_context():
        rows = SuperadminAuditLog.query.filter_by(
            action="create_feature_flag",
            target_id="audited_flag",
        ).all()
        assert len(rows) >= 1
