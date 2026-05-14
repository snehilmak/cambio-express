"""Drilldown migration Batch 2 — top-customers, top-senders,
top-recipients move to React.

Same migration shape as Batch 1: GET 301s to /app/*, CSV exports
stay on Flask. The SPA reads /api/v2/reports/top-customers (with
sort_by=count for the Top Senders variant) and
/api/v2/reports/top-recipients.
"""


_MIGRATED_BATCH = [
    "top-customers",
    "top-senders",
    "top-recipients",
]


def _admin_session_login(client, store_id):
    from api.Modules.Tenancy.Models import Store, User
    from app import db
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
