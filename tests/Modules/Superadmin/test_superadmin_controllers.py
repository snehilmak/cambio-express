"""HTTP integration tests for the Superadmin Controllers.

Mounts at /api/v2/superadmin/*. First slice ships the stores list.
"""


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
    """Seeded superadmin uses store_id=None and has no TOTP enrolled,
    so the SPA-31 2FA gate falls through to a real access token."""
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "superadmin",
            "password": "super2025!",
            "store_id": None,
        },
    )
    return resp.get_json()["access_token"]


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
    from app import Store, db, app as flask_app
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
