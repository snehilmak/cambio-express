"""HTTP integration tests for the admin referrals endpoint.

Powers /app/account/referrals. Lazily mints a ReferralCode on a
paid admin's first visit; trial admins get a 409 the SPA renders
as an upsell card. Mirrors the legacy admin_referrals route.
"""


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _put_on_paid_plan(store_id, plan="basic"):
    """Most tests need an active paid plan because the referrals
    feature gates on store_has_paid_plan."""
    from app import Store, app as flask_app, db
    with flask_app.app_context():
        s = db.session.get(Store, store_id)
        s.plan = plan
        db.session.commit()


# ── auth gating ─────────────────────────────────────────────


def test_referrals_requires_jwt(client):
    resp = client.get("/api/v2/admin/referrals")
    assert resp.status_code == 401


def test_referrals_rejects_superadmin(client):
    """Superadmin JWT carries no store scope — needs a store_id
    to mint a code, so it 403s."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/admin/referrals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── trial gate ──────────────────────────────────────────────


def test_referrals_409_for_trial_store(client, test_store_id):
    """Trial-plan stores get a 409. The SPA renders an upsell
    card pointing at /app/subscribe — see CLAUDE.md invariant
    #12 (referrals are paid-plan only)."""
    # Test fixture seeds the store on `trial` already, but be
    # explicit so a future fixture change doesn't silently flip
    # this expectation.
    from app import Store, app as flask_app, db
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        s.plan = "trial"
        db.session.commit()
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/referrals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert "subscription" in resp.get_json()["detail"].lower()


# ── happy path ──────────────────────────────────────────────


def test_referrals_lazily_mints_code_on_first_visit(
    client, test_store_id,
):
    """First visit by a paid admin should mint a fresh
    ReferralCode (idempotent — second visit returns the same
    code)."""
    _put_on_paid_plan(test_store_id)
    token = _login(client, test_store_id)
    body1 = client.get(
        "/api/v2/admin/referrals",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body1["code"]
    assert body1["is_active"] is True
    assert body1["reward_self_cents"] >= 0
    assert body1["reward_referee_cents"] >= 0
    # Second visit: same code (idempotent).
    body2 = client.get(
        "/api/v2/admin/referrals",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body2["code"] == body1["code"]


def test_referrals_share_url_includes_code(
    client, test_store_id,
):
    """The share_url must end with `?ref=<code>` so a copied
    link drops the recipient onto /signup with the code
    pre-filled."""
    _put_on_paid_plan(test_store_id)
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/referrals",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert "/signup" in body["share_url"]
    assert f"ref={body['code']}" in body["share_url"]


def test_referrals_starts_with_zero_redemptions(
    client, test_store_id,
):
    _put_on_paid_plan(test_store_id)
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/referrals",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["redemptions"] == []
    assert body["redeemed_count"] == 0
    assert body["credits_earned_cents"] == 0


def test_referrals_includes_redemption_history(
    client, test_store_id,
):
    """A redemption with self_credit_applied_at populated should
    surface in the history with self_credit_applied=True."""
    from datetime import datetime
    from app import (
        ReferralCode, ReferralRedemption, Store,
        app as flask_app, db,
    )
    _put_on_paid_plan(test_store_id)
    with flask_app.app_context():
        # Mint a referral code directly so we can attach a
        # redemption row to it.
        rc = ReferralCode(
            owner_store_id=test_store_id, code="TESTREF",
            reward_self_cents=10000, reward_referee_cents=5000,
            is_active=True, redeemed_count=1,
        )
        db.session.add(rc); db.session.flush()
        # Need a referee store to satisfy the FK.
        ref_store = Store(
            name="Referee", slug="referee-test", plan="basic",
        )
        db.session.add(ref_store); db.session.flush()
        red = ReferralRedemption(
            referral_code_id=rc.id,
            referee_store_id=ref_store.id,
            redeemed_at=datetime.utcnow(),
            self_credit_applied_at=datetime.utcnow(),
            stripe_self_txn_id="cust_bal_txn_test",
        )
        db.session.add(red); db.session.commit()
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/referrals",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["code"] == "TESTREF"
    assert body["redeemed_count"] == 1
    assert body["credits_earned_cents"] == 10000
    assert len(body["redemptions"]) == 1
    row = body["redemptions"][0]
    assert row["self_credit_applied"] is True
    assert row["referee_credit_applied"] is False
    assert row["stripe_self_txn_id"] == "cust_bal_txn_test"


# ── Flask redirect ──────────────────────────────────────────


def test_legacy_admin_referrals_redirects_to_app(
    logged_in_client,
):
    resp = logged_in_client.get(
        "/account/referrals", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/account/referrals"
