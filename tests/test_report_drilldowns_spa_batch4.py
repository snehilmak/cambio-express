"""Drilldown migration Batch 4 — audit + banking move to React.

Seven reports gain SPA wrappers + new /api/v2/reports/<slug>
endpoints (none of these had API endpoints yet):

  - returned-check-status
  - bank-transactions-breakdown
  - daily-drops
  - check-deposits
  - bank-rule-audit
  - bank-charges-by-account
  - period-comparison (takes optional ?compare_from=&compare_to=)
"""


_MIGRATED_BATCH = [
    "returned-check-status",
    "bank-transactions-breakdown",
    "daily-drops",
    "check-deposits",
    "bank-rule-audit",
    "bank-charges-by-account",
    "period-comparison",
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


def _admin_jwt(client, store_id):
    return client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": store_id},
    ).get_json()["access_token"]


def test_admin_drilldown_routes_redirect_to_spa(client, test_store_id):
    _admin_session_login(client, test_store_id)
    for slug in _MIGRATED_BATCH:
        resp = client.get(f"/reports/{slug}", follow_redirects=False)
        assert resp.status_code == 301, slug
        assert resp.headers["Location"] == f"/app/reports/{slug}", slug


def test_admin_drilldown_csv_routes_on_fastapi(client, test_store_id):
    from tests.conftest import login_admin
    jwt = login_admin(client, test_store_id)
    headers = {"Authorization": f"Bearer {jwt}"}
    for slug in _MIGRATED_BATCH:
        resp = client.get(
            f"/api/v2/reports/{slug}.csv?store_ids={test_store_id}",
            headers=headers,
        )
        assert resp.status_code == 200, slug
        assert resp.mimetype == "text/csv", slug


def test_new_api_endpoints_return_envelope(client, test_store_id):
    _admin_session_login(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    headers = {"Authorization": f"Bearer {jwt}"}
    for slug in _MIGRATED_BATCH:
        resp = client.get(
            f"/api/v2/reports/{slug}?store_ids={test_store_id}",
            headers=headers,
        )
        assert resp.status_code == 200, (slug, resp.get_data(as_text=True))
        body = resp.get_json()
        assert "rows" in body, slug
        assert "totals" in body, slug
