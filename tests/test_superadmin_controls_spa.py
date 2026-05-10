"""Superadmin controls hub SPA migration contract.

The /superadmin/controls Flask route used to render a 1,290-line
Jinja template with seven tabs (overview / stores / discounts /
feature flags / announcements / TV catalogs / send-test-email).
The GET now 301s to /app/superadmin/controls (a thin SPA hub
that pulls KPIs from /api/v2/dashboard/summary and links to the
existing dedicated SPA routes for Stores, Audit Log,
Announcements, and Reports).

The Discounts / Feature Flags / TV Catalogs admin UIs haven't
been ported to dedicated SPA routes yet — their POST mutation
endpoints stay live on Flask and the SPA hub marks them as
"Coming soon" without dead links.

The legacy `?tab=audit` carve-out preserves any superadmin
bookmark that landed on the old audit-log tab; it still bounces
straight to /superadmin/audit-log.
"""


def _superadmin_session(client):
    from app import User
    with client.application.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa_id = sa.id
    with client.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"] = "superadmin"
        s["store_id"] = None


def test_superadmin_controls_redirects_to_spa(client):
    _superadmin_session(client)
    resp = client.get("/superadmin/controls", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/superadmin/controls"


def test_superadmin_controls_preserves_query_string(client):
    _superadmin_session(client)
    resp = client.get(
        "/superadmin/controls?tab=stores&page=2", follow_redirects=False,
    )
    assert resp.status_code == 301
    # Query string survives so deep-linked URLs land in the right state.
    assert resp.headers["Location"].startswith("/app/superadmin/controls?")
    assert "tab=stores" in resp.headers["Location"]
    assert "page=2" in resp.headers["Location"]


def test_superadmin_controls_audit_tab_keeps_legacy_carve_out(client):
    """The Audit Log lives at /superadmin/reports/audit-log (a
    Report Center entry, not a top-level superadmin route). The
    legacy `?tab=audit` query param stays a 302 to that audit-log
    URL so a saved bookmark doesn't bounce through /app first."""
    _superadmin_session(client)
    resp = client.get(
        "/superadmin/controls?tab=audit", follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "audit-log" in resp.headers["Location"]


def test_superadmin_controls_requires_superadmin(client, test_store_id):
    """A store admin hitting /superadmin/controls gets bounced — the
    @superadmin_required decorator runs before the 301."""
    from app import User, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = test_store_id
    resp = client.get("/superadmin/controls", follow_redirects=False)
    # Decorator flashes + redirects to /dashboard.
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers["Location"]
