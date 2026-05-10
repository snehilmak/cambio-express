"""Owner dashboard + store detail SPA migration contract tests.

The /owner/dashboard and /owner/store/<id> Flask landings 301 to
/app/owner/* now. The SPA fetches:

  - GET /api/v2/owner/dashboard?period={today,month,year}
  - GET /api/v2/owner/store/{id}?period={today,month,year}

Two Jinja templates retired (owner_dashboard.html, owner_store_detail.html).
"""
from datetime import date


def _seed_owner_with_store(client):
    """Mint an owner user with one linked store + a JWT for it."""
    from app import Store, StoreOwnerLink, Transfer, User, db
    with client.application.app_context():
        s = Store(name="OS Store", slug="os-store-spa", plan="pro",
                  billing_cycle="monthly")
        db.session.add(s); db.session.commit()
        sid = s.id
        o = User(username="os-owner@x.com", full_name="OS Owner",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=sid))
        # Seed transfers: $300 Intermex Sent today, $9999 Canceled
        # today (must NOT count toward volume), $50 Maxi yesterday.
        from app import User as U
        admin = U.query.filter_by(username="admin@test.com").first()
        admin_id = admin.id if admin else oid
        db.session.add(Transfer(
            store_id=sid, created_by=admin_id, send_date=date.today(),
            company="Intermex", sender_name="A",
            send_amount=300.0, fee=3.0, status="Sent",
        ))
        db.session.add(Transfer(
            store_id=sid, created_by=admin_id, send_date=date.today(),
            company="Intermex", sender_name="B",
            send_amount=9999.0, fee=1.0, status="Canceled",
        ))
        db.session.commit()
    jwt = client.post(
        "/api/v2/auth/login",
        json={"username": "os-owner@x.com", "password": "ownerpass123",
              "store_id": None},
    ).get_json()["access_token"]
    return jwt, sid, oid


# ── Legacy redirects ─────────────────────────────────────────


def test_owner_dashboard_redirects_to_spa(client):
    """Unauthed: bounces to login. We test the contract through an
    authed owner session so the redirect-to-login path doesn't fire."""
    from app import User, db
    with client.application.app_context():
        o = User(username="dash-spa@x.com", full_name="Dash",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    resp = client.get("/owner/dashboard", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/owner/dashboard"


def test_owner_dashboard_preserves_period_query_string(client):
    from app import User, db
    with client.application.app_context():
        o = User(username="dash-spa-q@x.com", full_name="Dash",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    resp = client.get("/owner/dashboard?period=year", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/owner/dashboard?period=year"


# ── /api/v2/owner/dashboard envelope ─────────────────────────


def test_dashboard_envelope_excludes_canceled_volume(client):
    jwt, sid, _ = _seed_owner_with_store(client)
    resp = client.get(
        "/api/v2/owner/dashboard?period=today",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    # Canceled transfers MUST NOT inflate the volume rollup —
    # invariant matches the legacy view.
    assert body["agg_volume"] == 300.0
    assert body["agg_transfers"] == 1
    assert body["store_count"] == 1
    assert body["stores"][0]["id"] == sid


def test_dashboard_envelope_period_filter(client):
    jwt, _, _ = _seed_owner_with_store(client)
    resp = client.get(
        "/api/v2/owner/dashboard?period=month",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    # Period stamp echoes back in the period field.
    assert body["period"] == "month"


def test_dashboard_requires_owner_role(client, test_store_id):
    """An admin JWT can't hit /api/v2/owner/dashboard — owner-only."""
    jwt = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": test_store_id},
    ).get_json()["access_token"]
    resp = client.get(
        "/api/v2/owner/dashboard",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 403


# ── /api/v2/owner/store/{id} envelope ────────────────────────


def test_store_detail_envelope(client):
    jwt, sid, _ = _seed_owner_with_store(client)
    resp = client.get(
        f"/api/v2/owner/store/{sid}?period=today",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["store"]["id"] == sid
    assert body["period"] == "today"
    # Company breakdown excludes canceled.
    intermex = next(
        r for r in body["company_rows"] if r["company"] == "Intermex"
    )
    assert intermex["volume"] == 300.0
    assert intermex["count"] == 1
    # Recent transfers list comes back.
    assert len(body["recent_transfers"]) >= 1
    # 30-day series is the right shape.
    assert len(body["daily_labels"]) == 30
    assert len(body["over_short_data"]) == 30
    assert len(body["receipts_data"]) == 30


def test_store_detail_blocks_unrelated_store(client):
    """An owner can't drill into a store they're not linked to —
    the API returns 404 (parity with the legacy 302-bounce, just
    a more API-shaped status)."""
    from app import Store, User, db
    jwt, _, _ = _seed_owner_with_store(client)
    with client.application.app_context():
        other = Store(name="Other", slug="other-spa", plan="pro")
        db.session.add(other); db.session.commit()
        other_id = other.id
    resp = client.get(
        f"/api/v2/owner/store/{other_id}",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 404


def test_store_detail_requires_owner_role(client, test_store_id):
    jwt = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": test_store_id},
    ).get_json()["access_token"]
    resp = client.get(
        f"/api/v2/owner/store/{test_store_id}",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 403
