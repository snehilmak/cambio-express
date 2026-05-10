"""Drilldown migration Batch 3 — operations & fees move to React.

Six reports gain SPA wrappers + new /api/v2/reports/{slug}
endpoints (where they didn't exist):

  - new-vs-returning (new API endpoint)
  - by-destination-country (API was already there)
  - fees-vs-tax (new)
  - high-value-transfers (new, takes ?threshold=)
  - cancelled-transfers (new)
  - ach-volume (new)
"""


_MIGRATED_BATCH = [
    "new-vs-returning",
    "by-destination-country",
    "fees-vs-tax",
    "high-value-transfers",
    "cancelled-transfers",
    "ach-volume",
]


def _admin_session_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"; s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


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


def test_admin_drilldown_csv_routes_stay_on_flask(client, test_store_id):
    _admin_session_login(client, test_store_id)
    for slug in _MIGRATED_BATCH:
        resp = client.get(f"/reports/{slug}.csv")
        assert resp.status_code == 200, slug
        assert resp.mimetype == "text/csv", slug


def test_new_api_endpoints_return_envelope(client, test_store_id):
    """The five new endpoints all return a `{rows, totals}` envelope."""
    _admin_session_login(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    headers = {"Authorization": f"Bearer {jwt}"}
    for api_slug in (
        "new-vs-returning", "fees-vs-tax", "cancelled-transfers",
        "ach-volume",
    ):
        resp = client.get(
            f"/api/v2/reports/{api_slug}?store_ids={test_store_id}",
            headers=headers,
        )
        assert resp.status_code == 200, api_slug
        body = resp.get_json()
        assert "rows" in body, api_slug
        assert "totals" in body, api_slug


def test_high_value_endpoint_accepts_threshold(client, test_store_id):
    _admin_session_login(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    resp = client.get(
        f"/api/v2/reports/high-value-transfers"
        f"?store_ids={test_store_id}&threshold=5000",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["threshold"] == 5000
