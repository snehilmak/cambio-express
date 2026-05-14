"""Drilldown migration Batch 5 — final batch.

Migrates:

  - 2 admin stragglers: employee-activity, period-pl
  - 20 superadmin BI reports via a single generic
    /api/v2/superadmin/reports/<slug> endpoint that dispatches
    by slug into the matching Service function. The SPA renders
    a generic drilldown (`SuperadminBIDrilldown.tsx`) that
    auto-derives KPIs from totals + columns from rows.

All Jinja report templates retired. The cleanup phase removes
the generic _report_page.html chrome too.
"""


_ADMIN_BATCH = ["employee-activity", "period-pl"]
_SA_BATCH = [
    "active-stores-by-plan", "signup-funnel", "login-activity",
    "mrr-arr", "churn-cohort", "conversion-rate", "time-to-convert",
    "trial-expiry-timing", "bank-sync-adoption", "tv-display-adoption",
    "owner-adoption", "passkey-adoption", "password-resets",
    "suspended-stores", "retention-queue", "refunds", "failed-payments",
    "payouts", "dau-mau", "webhook-health",
]


def _admin_session_login(client, store_id):
    from api.Modules.Tenancy.Models import Store, User
    from tests._app import db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"; s.billing_cycle = "monthly"
        db.session.commit()


def _superadmin_session(client):
    from api.Modules.Tenancy.Models import User
    with client.application.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa_id = sa.id


def test_admin_stragglers_redirect_to_spa(client, test_store_id):
    _admin_session_login(client, test_store_id)
    for slug in _ADMIN_BATCH:
        resp = client.get(f"/reports/{slug}", follow_redirects=False)
        assert resp.status_code == 301, slug
        assert resp.headers["Location"] == f"/app/reports/{slug}", slug


def test_admin_stragglers_csv_on_fastapi(client, test_store_id):
    from tests.conftest import login_admin
    jwt = login_admin(client, test_store_id)
    headers = {"Authorization": f"Bearer {jwt}"}
    for slug in _ADMIN_BATCH:
        resp = client.get(
            f"/api/v2/reports/{slug}.csv?store_ids={test_store_id}",
            headers=headers,
        )
        assert resp.status_code == 200, slug
        assert resp.mimetype == "text/csv", slug


def test_every_superadmin_report_redirects_to_spa(client):
    _superadmin_session(client)
    for slug in _SA_BATCH:
        resp = client.get(
            f"/superadmin/reports/{slug}", follow_redirects=False,
        )
        assert resp.status_code == 301, slug
        assert resp.headers["Location"].startswith(
            f"/app/superadmin/reports/{slug}",
        ), slug


def test_superadmin_csv_on_fastapi(client):
    from tests.conftest import login_superadmin
    jwt = login_superadmin(client)
    headers = {"Authorization": f"Bearer {jwt}"}
    for slug in _SA_BATCH:
        resp = client.get(
            f"/api/v2/superadmin/reports/{slug}.csv", headers=headers,
        )
        assert resp.status_code == 200, (
            slug, resp.get_data(as_text=True)[:200],
        )
        assert resp.mimetype == "text/csv", slug


def test_generic_superadmin_api_returns_envelope(client):
    """The new /api/v2/superadmin/reports/<slug> endpoint dispatches
    into the right Service for every wired BI slug."""
    from tests.conftest import login_superadmin
    jwt = login_superadmin(client)
    headers = {"Authorization": f"Bearer {jwt}"}
    for slug in _SA_BATCH:
        resp = client.get(
            f"/api/v2/superadmin/reports/{slug}", headers=headers,
        )
        assert resp.status_code == 200, (
            slug, resp.get_data(as_text=True),
        )
        body = resp.get_json()
        assert "rows" in body, slug
        assert "totals" in body, slug


def test_generic_superadmin_api_404s_unknown_slug(client):
    from tests.conftest import login_superadmin
    jwt = login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/reports/no-such-report",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 404


def test_generic_superadmin_api_requires_superadmin(client, test_store_id):
    _admin_session_login(client, test_store_id)
    jwt = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": test_store_id},
    ).get_json()["access_token"]
    resp = client.get(
        "/api/v2/superadmin/reports/mrr-arr",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 403
