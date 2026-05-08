"""HTTP integration tests for /api/v2/superadmin/discounts.

Read-only list + activation toggle. Stripe coupon mint stays on the
legacy site, so these endpoints never touch Stripe — that's why
the tests don't need to monkeypatch the SDK.
"""
from datetime import datetime, timedelta


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
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": "superadmin", "password": "super2025!",
              "store_id": None},
    )
    return resp.get_json()["access_token"]


def _seed_code(**overrides):
    """Insert a DiscountCode row. Defaults give a 20% off forever code
    that's active and uncapped."""
    from app import DiscountCode, app as flask_app, db
    with flask_app.app_context():
        d = DiscountCode(
            code=overrides.pop("code", f"TEST{datetime.utcnow().timestamp()}"),
            label=overrides.pop("label", "Test promo"),
            percent_off=overrides.pop("percent_off", 20),
            amount_off_cents=overrides.pop("amount_off_cents", None),
            duration=overrides.pop("duration", "forever"),
            duration_in_months=overrides.pop("duration_in_months", None),
            max_redemptions=overrides.pop("max_redemptions", None),
            redeemed_count=overrides.pop("redeemed_count", 0),
            expires_at=overrides.pop("expires_at", None),
            is_active=overrides.pop("is_active", True),
        )
        for k, v in overrides.items():
            setattr(d, k, v)
        db.session.add(d)
        db.session.commit()
        return d.id


# ── List endpoint ───────────────────────────────────────────


def test_list_discounts_requires_jwt(client):
    resp = client.get("/api/v2/superadmin/discounts")
    assert resp.status_code == 401


def test_list_discounts_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_list_discounts_empty_envelope(client):
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {"rows", "total"}
    assert body["rows"] == []
    assert body["total"] == 0


def test_list_discounts_returns_newest_first(client):
    """Two codes with different created_at — newer one should come first."""
    from app import DiscountCode, app as flask_app, db
    with flask_app.app_context():
        old = DiscountCode(
            code="OLDONE", percent_off=10, duration="once",
            created_at=datetime.utcnow() - timedelta(days=2),
        )
        new = DiscountCode(
            code="NEWONE", percent_off=15, duration="once",
            created_at=datetime.utcnow(),
        )
        db.session.add_all([old, new]); db.session.commit()

    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    codes = [r["code"] for r in body["rows"]]
    assert codes == ["NEWONE", "OLDONE"]
    assert body["total"] == 2


def test_list_discounts_value_label_percent(client):
    _seed_code(code="PCT20", percent_off=20, amount_off_cents=None)
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(r for r in body["rows"] if r["code"] == "PCT20")
    assert row["value_label"] == "20% off"
    assert row["percent_off"] == 20
    assert row["amount_off_cents"] is None


def test_list_discounts_value_label_amount(client):
    _seed_code(code="AMT500", percent_off=None, amount_off_cents=500)
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(r for r in body["rows"] if r["code"] == "AMT500")
    assert row["value_label"] == "$5.00 off"


def test_is_redeemable_active_uncapped(client):
    _seed_code(code="REDEEM1", is_active=True)
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(r for r in body["rows"] if r["code"] == "REDEEM1")
    assert row["is_active"] is True
    assert row["is_redeemable"] is True


def test_is_redeemable_false_when_inactive(client):
    _seed_code(code="OFF1", is_active=False)
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(r for r in body["rows"] if r["code"] == "OFF1")
    assert row["is_active"] is False
    assert row["is_redeemable"] is False


def test_is_redeemable_false_when_expired(client):
    _seed_code(
        code="EXP1", is_active=True,
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(r for r in body["rows"] if r["code"] == "EXP1")
    assert row["is_active"] is True
    assert row["is_redeemable"] is False


def test_is_redeemable_false_when_capped(client):
    _seed_code(
        code="CAP1", is_active=True,
        max_redemptions=5, redeemed_count=5,
    )
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/discounts",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(r for r in body["rows"] if r["code"] == "CAP1")
    assert row["is_redeemable"] is False


# ── Toggle endpoint ─────────────────────────────────────────


def test_toggle_requires_jwt(client):
    discount_id = _seed_code(code="TOG1")
    resp = client.post(
        f"/api/v2/superadmin/discounts/{discount_id}/toggle",
        json={"is_active": False},
    )
    assert resp.status_code == 401


def test_toggle_rejects_admin_role(client, test_store_id):
    discount_id = _seed_code(code="TOG2")
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/superadmin/discounts/{discount_id}/toggle",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_toggle_flips_is_active_off(client):
    from app import DiscountCode, app as flask_app
    discount_id = _seed_code(code="TOG3", is_active=True)
    token = _login_superadmin(client)
    resp = client.post(
        f"/api/v2/superadmin/discounts/{discount_id}/toggle",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["discount"]["is_active"] is False
    assert body["discount"]["is_redeemable"] is False
    with flask_app.app_context():
        from app import db as _db
        d = _db.session.get(DiscountCode, discount_id)
        assert d.is_active is False


def test_toggle_flips_is_active_on(client):
    from app import DiscountCode, app as flask_app
    discount_id = _seed_code(code="TOG4", is_active=False)
    token = _login_superadmin(client)
    resp = client.post(
        f"/api/v2/superadmin/discounts/{discount_id}/toggle",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["discount"]["is_active"] is True
    with flask_app.app_context():
        from app import db as _db
        d = _db.session.get(DiscountCode, discount_id)
        assert d.is_active is True


def test_toggle_404_on_unknown_id(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/superadmin/discounts/99999/toggle",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
