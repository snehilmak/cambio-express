"""Drilldown migration Batch 1 — sales-by-{company,service-type,employee}
and cashier-productivity move to React.

GET /reports/<slug> + GET /owner/reports/<slug> 301 to /app/*.
CSV exports (/reports/<slug>.csv) stay on Flask as direct
downloads. The data envelope is fetched by the SPA from
/api/v2/reports/<api-slug>.
"""


_MIGRATED_BATCH = [
    ("sales-by-company",      "sales-by-company"),
    ("sales-by-service-type", "sales-by-service-type"),
    ("sales-by-employee",     "sales-by-employee"),
    ("cashier-productivity",  "cashier-productivity"),
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


def test_admin_drilldown_routes_redirect_to_spa(client, test_store_id):
    _admin_session_login(client, test_store_id)
    for flask_slug, _api_slug in _MIGRATED_BATCH:
        resp = client.get(
            f"/reports/{flask_slug}", follow_redirects=False,
        )
        assert resp.status_code == 301, f"slug={flask_slug}"
        assert resp.headers["Location"] == f"/app/reports/{flask_slug}", (
            f"slug={flask_slug}"
        )


def test_admin_drilldown_csv_routes_stay_on_flask(client, test_store_id):
    """CSV exports MUST stay on Flask — the SPA links to them as
    `download` attributes."""
    _admin_session_login(client, test_store_id)
    for flask_slug, _api_slug in _MIGRATED_BATCH:
        resp = client.get(f"/reports/{flask_slug}.csv")
        assert resp.status_code == 200, f"slug={flask_slug}"
        assert resp.mimetype == "text/csv", f"slug={flask_slug}"


def test_owner_drilldown_routes_redirect_to_spa(client):
    """Owner-side mirror routes 301 the GET to /app/owner/reports/<slug>."""
    from app import Store, StoreOwnerLink, User, db
    with client.application.app_context():
        s = Store(name="Drilldown Owner Store",
                  slug="drilldown-owner-store", plan="pro",
                  billing_cycle="monthly")
        db.session.add(s); db.session.commit()
        sid = s.id
        o = User(username="drilldown-owner@x.com",
                 full_name="Drilldown Owner",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=sid))
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    for flask_slug, _api_slug in _MIGRATED_BATCH:
        resp = client.get(
            f"/owner/reports/{flask_slug}", follow_redirects=False,
        )
        assert resp.status_code == 301, f"slug={flask_slug}"
        assert resp.headers["Location"] == f"/app/owner/reports/{flask_slug}", (
            f"slug={flask_slug}"
        )


def test_drilldown_redirect_preserves_period_query_string(
    client, test_store_id,
):
    _admin_session_login(client, test_store_id)
    resp = client.get(
        "/reports/sales-by-company?from=2026-01-01&to=2026-01-31",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    target = resp.headers["Location"]
    assert target.startswith("/app/reports/sales-by-company?")
    assert "from=2026-01-01" in target
    assert "to=2026-01-31" in target
