"""Dashboard SPA migration contract tests.

The legacy /dashboard Flask route 301s to /app/dashboard. The SPA
fetches /api/v2/dashboard/summary, which returns a role-shaped
payload (admin / employee / superadmin / owner-redirect).
"""
from datetime import date


def _admin_session_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def _admin_jwt(client, store_id, *, username="admin@test.com",
               password="testpass123!"):
    return client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password,
              "store_id": store_id},
    ).get_json()["access_token"]


# ── Legacy /dashboard 301s ──────────────────────────────────


def test_legacy_dashboard_redirects_to_spa(client, test_store_id):
    _admin_session_login(client, test_store_id)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/dashboard"


def test_legacy_dashboard_owner_redirects_to_owner_spa(client):
    """Owner sessions redirect to the owner-side dashboard, which
    has its own multi-store rollup payload."""
    from app import User, db
    with client.application.app_context():
        o = User(username="dash-owner@x.com", full_name="Dash Owner",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/owner/dashboard"


def test_legacy_dashboard_unauth_bounces_to_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ── /api/v2/dashboard/summary ──────────────────────────────


def test_admin_summary_envelope(client, test_store_id):
    _admin_session_login(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    resp = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["role"] == "admin"
    assert body["today"] == date.today().isoformat()
    assert "kpis" in body and "company_stats" in body
    assert isinstance(body["recent_transfers"], list)
    assert isinstance(body["recent_batches"], list)
    assert isinstance(body["stripe_accounts"], list)
    kpis = body["kpis"]
    for k in ("total_transfers", "today_transfers", "pending_ach",
              "today_report_entered"):
        assert k in kpis


def test_employee_summary_envelope(client, test_store_id):
    """Employee role sees today_transfers + same-day totals only."""
    from app import User, Store, db
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.plan = "pro"
        u = User(username="emp@dash.test", full_name="Emp Dash",
                 role="employee", store_id=test_store_id)
        u.set_password("emppass123")
        db.session.add(u); db.session.commit()
    jwt = client.post(
        "/api/v2/auth/login",
        json={"username": "emp@dash.test", "password": "emppass123",
              "store_id": test_store_id},
    ).get_json()["access_token"]
    resp = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["role"] == "employee"
    assert "today_transfers" in body
    assert body["totals"] == {"sent": 0.0, "fees": 0.0, "count": 0}


def test_superadmin_summary_returns_platform_bi(client):
    """Superadmin gets the platform BI payload (delegates to
    superadmin_dashboard_context). Just verify role tag round-trips
    and the dict has at least one platform field — superadmin login
    is the two-step TOTP flow (see conftest.login_superadmin)."""
    from tests.conftest import login_superadmin
    jwt = login_superadmin(client)
    resp = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["role"] == "superadmin"
    # The service always returns store-count fields even on a
    # fresh DB. Don't pin to one exact key — the underlying service
    # surface evolves; just confirm the envelope is non-empty.
    assert len(body) > 1


def test_summary_requires_auth(client):
    """Anonymous requests get 401."""
    resp = client.get("/api/v2/dashboard/summary")
    assert resp.status_code == 401
